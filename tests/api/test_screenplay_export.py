"""
L4 API：剧本查询端点 + 4 个导出端点。

PR 04 在这里只固化了「路由已注册 + 未知 task_id → 404」两条基线；
PR 09 补上真正的价值：**断言响应体是合法的目标格式**，而不只是「状态码 200」。

覆盖对照（`Looploop_Test_PR_Plan.md` PR 09）：
    GET /api/screenplay/{id}     → 200 可 Pydantic 校验 / 与源数据逐字段一致 /
                                   未完成态 / error → 500 / 404
    GET .../export/yaml          → content-type + disposition + safe_load 往返一致 + 中文不转义
    GET .../export/word          → PK 魔数 + python-docx 能打开 + 正文含标题
    GET .../export/manifest      → YAML 结构 + 字段契约
    GET .../export/zip           → is_zipfile + 成员齐全 + 内嵌素材清单
    4 个端点                     → 未知任务 404 / 任务无剧本 404 / 路由注册

为什么「能解析」比「200」值钱：导出端点最典型的回归是某次重构把
`Response(content=<dict>)` 直接传进去 —— 状态码照样 200，下游拿到一坨 Python repr。
只有真去 parse 才抓得住。
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
import yaml
from docx import Document

from backend.models import Screenplay
from tests.fakes.fake_llm import make_valid_screenplay_dict

EXPORT_KINDS = ["yaml", "word", "manifest", "zip"]

MANIFEST_TOP_LEVEL = {"meta", "characters", "scenes"}
MANIFEST_CHARACTER_FIELDS = {"name", "aliases", "role", "gender", "age", "description"}
#: 独立 manifest 端点的场景字段
MANIFEST_SCENE_FIELDS = {"location", "time_of_day", "atmosphere", "shot_count"}
#: zip 内嵌的那份素材清单少了 time_of_day —— 同一份数据在两处各自拼装导致的分叉，
#: 见 PR 描述「发现」。这里固化现状：任何一侧再变都必须被察觉。
ZIP_MANIFEST_SCENE_FIELDS = {"location", "atmosphere", "shot_count"}


# ============================================================
# GET /api/screenplay/{task_id}
# ============================================================

def test_get_screenplay_returns_pydantic_valid_screenplay(
    client, completed_task, completed_task_screenplay
):
    resp = client.get(f"/api/screenplay/{completed_task}")

    assert resp.status_code == 200, resp.text

    screenplay = Screenplay.model_validate(resp.json())

    assert screenplay.meta.title == completed_task_screenplay["meta"]["title"]
    assert screenplay.scenes, "剧本没有场景"
    assert screenplay.characters, "角色表为空"


def test_get_screenplay_matches_seeded_source_data(
    client, completed_task, completed_task_screenplay
):
    """读回来必须与预置的源数据**逐字段一致**——不是「有 meta 就行」。"""
    body = client.get(f"/api/screenplay/{completed_task}").json()

    assert Screenplay.model_validate(body).model_dump() == completed_task_screenplay


def test_get_screenplay_404_for_unknown_task(client):
    resp = client.get("/api/screenplay/never-existed")

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert resp.json()["detail"] == "任务不存在"


def test_get_screenplay_returns_progress_while_unfinished(client, seeded_task):
    """
    未完成的任务不报错，而是回 `{status, progress}`。

    这是前端的核心契约：同一个 URL 既要能问「好了吗」，也要能拿「结果」，
    靠 status 区分。断言里刻意检查「没有 meta」——否则前端会拿到半成品当真剧本。
    """
    resp = client.get(f"/api/screenplay/{seeded_task}")

    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["status"] == "pending", f"got {body}"
    assert body["progress"] == 0.0, f"got {body}"
    assert "meta" not in body, f"未完成的任务不该返回剧本字段：{body}"


def test_get_screenplay_500_for_failed_task(client, failed_task):
    """
    `status=error` 必须 500 并把原因带出来，而不是 200 + 空剧本。

    这是突变扫描的漏网项 M14：把这条分支删掉，此前整套测试依然全绿。
    前端据此区分「还在跑」与「跑挂了」——两者都回 200 会让进度条永远转下去。
    """
    resp = client.get(f"/api/screenplay/{failed_task}")

    assert resp.status_code == 500, f"got {resp.status_code}"
    assert resp.json()["detail"] == "模拟管线崩溃", f"got {resp.json()}"


# ============================================================
# 4 个导出端点：404 与路由注册
# ============================================================

@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_returns_404_for_unknown_task(client, kind):
    """任务不存在 → 404。"""
    resp = client.get(f"/api/screenplay/never-existed/export/{kind}")

    assert resp.status_code == 404, f"{kind}: got {resp.status_code}"
    assert resp.json().get("detail"), f"{kind}: 404 应带 detail 说明"


@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_returns_404_when_task_has_no_screenplay(client, seeded_task, kind):
    """
    任务存在但还没产出剧本 → 也是 404，但 detail 不同。

    区分这两条 404 是有意义的：前者是「你 id 写错了」，后者是「再等等」。
    """
    resp = client.get(f"/api/screenplay/{seeded_task}/export/{kind}")

    assert resp.status_code == 404, f"{kind}: got {resp.status_code}"
    assert resp.json()["detail"] == "剧本不存在", f"{kind}: got {resp.json()}"


@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_export_route_is_registered(client, kind):
    """路由存在性的精确检查——盯 OpenAPI schema，而不是从 404 反推。"""
    paths = client.get("/openapi.json").json()["paths"]

    assert f"/api/screenplay/{{task_id}}/export/{kind}" in paths, (
        f"{kind}: 路由未注册，已注册路径：{sorted(paths)}"
    )


# ============================================================
# export/yaml
# ============================================================

def test_export_yaml_is_parseable_and_round_trips(
    client, completed_task, completed_task_screenplay
):
    """YAML 必须能 safe_load，且往返后与源剧本逐字段一致（序列化没丢字段）。"""
    resp = client.get(f"/api/screenplay/{completed_task}/export/yaml")

    assert resp.status_code == 200, resp.text
    assert "yaml" in resp.headers["content-type"].lower(), resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"].lower(), (
        resp.headers["content-disposition"]
    )

    loaded = yaml.safe_load(resp.content.decode("utf-8"))

    assert loaded is not None, "导出的 YAML 解析为 None"
    assert Screenplay.model_validate(loaded).model_dump() == completed_task_screenplay, (
        "YAML 往返后与源剧本不一致——序列化丢了字段"
    )


def test_export_yaml_keeps_chinese_un_escaped(client, completed_task, completed_task_screenplay):
    """
    中文必须是**字面量**，不能是 \\uXXXX 转义（`allow_unicode=True` 的产物）。

    计划书建议「把 yaml 的 allow_unicode 改坏 → safe_load 断言应变红」，
    但实测**不会**：转义后的 `\\u539f\\u59cb` 依然是合法 YAML，safe_load 照样成功。
    所以要抓这个回归，就必须直接看原文。
    """
    raw = client.get(f"/api/screenplay/{completed_task}/export/yaml").content.decode("utf-8")
    title = completed_task_screenplay["meta"]["title"]

    assert title in raw, f"中文被转义，导出物不再是人类可读的 YAML：{raw[:200]!r}"


# ============================================================
# export/word
# ============================================================

def test_export_word_is_a_readable_docx(
    client, completed_task, completed_task_screenplay, tmp_path
):
    """
    Word 导出必须真的是 OOXML 包（PK 魔数）且能被 python-docx 打开。

    「以 PK 开头」这条断言就是用来抓「导出改成返回纯文本」这类回归的——
    那种情况下状态码和 content-type 都可能一切正常。
    """
    resp = client.get(f"/api/screenplay/{completed_task}/export/word")

    assert resp.status_code == 200, resp.text
    assert "wordprocessingml" in resp.headers["content-type"], resp.headers["content-type"]
    assert resp.content[:2] == b"PK", (
        f"不是 OOXML(zip) 容器，前 16 字节：{resp.content[:16]!r}"
    )

    path = tmp_path / "export.docx"
    path.write_bytes(resp.content)
    document = Document(str(path))          # 打不开就说明不是合法 docx

    assert len(document.paragraphs) > 0, "docx 里一个段落都没有"

    text = "\n".join(p.text for p in document.paragraphs)
    assert completed_task_screenplay["meta"]["title"] in text, (
        f"正文里找不到剧本标题；实际正文：{text[:200]!r}"
    )


# ============================================================
# export/manifest
# ============================================================

def test_export_manifest_has_expected_shape(client, completed_task, completed_task_screenplay):
    """
    ⚠️ 端点叫 manifest，产物其实是 **YAML** 而非计划书写的 JSON
    （实测 media_type 为 `application/x-yaml`）。
    """
    resp = client.get(f"/api/screenplay/{completed_task}/export/manifest")

    assert resp.status_code == 200, resp.text
    assert "yaml" in resp.headers["content-type"].lower(), resp.headers["content-type"]

    manifest = yaml.safe_load(resp.content.decode("utf-8"))

    assert set(manifest) == MANIFEST_TOP_LEVEL, f"got {sorted(manifest)}"
    assert manifest["meta"]["title"] == completed_task_screenplay["meta"]["title"]
    assert manifest["meta"]["version"] == "v0.4"

    expected_chars = {
        c["material_id"] or c["character_id"] for c in completed_task_screenplay["characters"]
    }
    assert set(manifest["characters"]) == expected_chars, (
        f"素材清单的角色 key 不对：{sorted(manifest['characters'])}"
    )
    for entry in manifest["characters"].values():
        assert set(entry) == MANIFEST_CHARACTER_FIELDS, f"got {sorted(entry)}"

    expected_scenes = {
        s["material_id"] or s["scene_id"] for s in completed_task_screenplay["scenes"]
    }
    assert set(manifest["scenes"]) == expected_scenes, (
        f"素材清单的场景 key 不对：{sorted(manifest['scenes'])}"
    )
    for entry in manifest["scenes"].values():
        assert set(entry) == MANIFEST_SCENE_FIELDS, f"got {sorted(entry)}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（PR 09 发现）：`export_manifest` 用 "
        "`c.get('material_id', c.get('character_id', '?'))` 取素材编号——"
        "`.get(key, default)` 只在**键不存在**时回落，而 `Character.material_id` 的模型默认值"
        "是空字符串 `''`，键一直存在，于是所有角色都映射到同一个 `''` key，后者覆盖前者："
        "素材清单静默丢人（N 个角色只剩 1 条）。"
        "修复应改用 `c.get('material_id') or c.get('character_id') or '?'`。"
        "修复后本用例 XPASS，strict 模式下即失败，强制摘掉标记。"
    ),
)
def test_manifest_keeps_distinct_entries_when_material_id_is_empty(client, task_factory):
    """两个都没有 material_id 的角色，应当各占一个素材清单条目。"""
    screenplay = make_valid_screenplay_dict()
    for character in screenplay["characters"]:
        character["material_id"] = ""

    probe_id = "ffff00000001"
    task_factory(probe_id, "清单回落探针", status="done", screenplay=screenplay)

    manifest = yaml.safe_load(
        client.get(f"/api/screenplay/{probe_id}/export/manifest").content.decode("utf-8")
    )

    assert len(manifest["characters"]) == 2, (
        f"两个角色被折叠成了 {len(manifest['characters'])} 条：{list(manifest['characters'])}"
    )


# ============================================================
# export/zip
# ============================================================

def test_export_zip_is_a_zip_with_expected_members(client, ascii_titled_task):
    resp = client.get(f"/api/screenplay/{ascii_titled_task}/export/zip")

    assert resp.status_code == 200, resp.text
    assert resp.content[:2] == b"PK", f"不是 zip：{resp.content[:16]!r}"

    buffer = BytesIO(resp.content)
    assert zipfile.is_zipfile(buffer), "zipfile 不认这个包"

    with zipfile.ZipFile(buffer) as archive:
        names = archive.namelist()

        assert len(names) >= 3, f"成员太少：{names}"
        assert any(n.endswith(".yaml") for n in names), names
        assert any(n.endswith(".docx") for n in names), names

        # 内嵌的剧本 YAML 也要能解析（不是塞了个空文件进去）
        script_name = next(n for n in names if "剧本" in n and n.endswith(".yaml"))
        script = yaml.safe_load(archive.read(script_name).decode("utf-8"))
        assert Screenplay.model_validate(script), f"{script_name} 内容不是合法剧本"

        # 内嵌的 docx 也要能被 python-docx 打开
        docx_name = next(n for n in names if n.endswith(".docx"))
        assert archive.read(docx_name)[:2] == b"PK", docx_name


def test_export_zip_embedded_manifest_fields(client, ascii_titled_task, ascii_titled_screenplay):
    """
    zip 内嵌的素材清单：固化它**少了 time_of_day** 这个现状。

    同一个 manifest 在 `export_manifest` 与 `export_zip` 里各拼了一遍（代码重复），
    两处的场景字段已经分叉。断言写成显式集合，任何一侧再变都会立刻现形。
    """
    resp = client.get(f"/api/screenplay/{ascii_titled_task}/export/zip")

    with zipfile.ZipFile(BytesIO(resp.content)) as archive:
        manifest_name = next(n for n in archive.namelist() if "素材清单" in n)
        manifest = yaml.safe_load(archive.read(manifest_name).decode("utf-8"))

    assert set(manifest) == MANIFEST_TOP_LEVEL, f"got {sorted(manifest)}"
    assert manifest["meta"]["title"] == ascii_titled_screenplay["meta"]["title"]

    expected_scenes = {
        s["material_id"] or s["scene_id"] for s in ascii_titled_screenplay["scenes"]
    }
    assert set(manifest["scenes"]) == expected_scenes

    for entry in manifest["scenes"].values():
        assert set(entry) == ZIP_MANIFEST_SCENE_FIELDS, (
            f"zip 内嵌清单的场景字段变了：{sorted(entry)}"
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（PR 09 发现，影响面大）：`export_zip` 把剧本标题拼进 "
        "`Content-Disposition: attachment; filename={title}_project.zip`，"
        "而 Starlette 用 latin-1 编码 header 值 → 中文标题直接抛 "
        "UnicodeEncodeError，端点 500，ZIP 完全导不出来。"
        "对一个中文产品来说这是主路径，而非边缘情况。"
        "修法是 RFC 6266 双写：ASCII 回退名 + `filename*=UTF-8''<percent-encoded>`。"
        "修复后本用例 XPASS，strict 模式下即失败，强制摘掉标记。"
    ),
)
def test_export_zip_handles_non_ascii_title(client, completed_task):
    """中文标题（真实使用场景）也必须能导出 ZIP。"""
    resp = client.get(f"/api/screenplay/{completed_task}/export/zip")

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert zipfile.is_zipfile(BytesIO(resp.content))
