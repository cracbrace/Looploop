"""
L4 API：任务管理簇 4 个端点。

覆盖对照（`Looploop_Test_PR_Plan.md` PR 08）：
    GET    /api/tasks                → 空列表 / 字段契约 / created_at 倒序 / 时区换算
    PATCH  /api/tasks/{id}/title     → 200 落库 / 去空白 / 404 / 422
    DELETE /api/tasks/{id}           → 200 真删 / 不存在 404 / 重复删 404
    PATCH  /api/screenplay/{id}      → 200 落库可回读 / 不越界改任务名 / 404 / 422

本文件是「13 个端点仅覆盖 3 个」这条 P0 缺口的第一次实质补齐。

两个来自**实测**而非计划书的关键点，都在下面标了注释：

1. **422 有两种形状。** FastAPI 校验层给出 `detail: list`；而 `routes.rename_task`
   是手工 `raise HTTPException(422, detail="Title cannot be empty")`，给出 `detail: str`。
   照 PR 04 的写法断言 `detail[0]["loc"]` 会在这里直接 TypeError。
2. **`PATCH /api/screenplay` 完全不校验剧本结构**：结构错误的 payload 拿到 200 并原样落库。
   已按「已知缺陷」用 strict xfail 固化为可执行证据（见文件末尾）。
"""

from __future__ import annotations

import pytest

from tests.fakes.fake_llm import make_valid_screenplay_dict

#: `GET /api/tasks` 的响应契约（即 `database.list_tasks()` 的 SELECT 列）。
#: 断言等集而非「包含」——多一个字段也应当在评审里被看见。
TASK_LIST_FIELDS = frozenset({
    "task_id", "title", "status", "progress", "stage", "message",
    "created_at", "original_text",
})


# ============================================================
# GET /api/tasks
# ============================================================

def test_tasks_returns_empty_list_on_fresh_db(client):
    """空库 → `[]`（而不是 404、null 或报错）。"""
    resp = client.get("/api/tasks")

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert resp.json() == []


def test_tasks_returns_contract_fields(client, seeded_task):
    """字段集合就是契约本身。"""
    payload = client.get("/api/tasks").json()

    assert len(payload) == 1, f"got {payload}"
    assert set(payload[0]) == TASK_LIST_FIELDS, (
        f"字段集合变了：多出 {set(payload[0]) - TASK_LIST_FIELDS}，"
        f"缺少 {TASK_LIST_FIELDS - set(payload[0])}"
    )
    assert payload[0]["task_id"] == seeded_task
    assert payload[0]["status"] == "pending"


def test_tasks_ordered_by_created_at_desc(client, tasks_with_explicit_times):
    """最新的排在前面——`ORDER BY created_at DESC` 的实际语义。"""
    payload = client.get("/api/tasks").json()

    assert [t["task_id"] for t in payload] == [
        "cccc00000003",  # 2024-01-03
        "cccc00000002",  # 2024-01-02
        "cccc00000001",  # 2024-01-01
    ], f"排序不对：{[(t['task_id'], t['created_at']) for t in payload]}"


def test_tasks_created_at_is_converted_to_beijing_time(client, task_factory):
    """
    created_at 必须是**真正换算过**的北京时间，而不是给 UTC 字符串贴个 +08:00 标签。

    这是突变扫描找出的覆盖空白之一：时区修复（pr/53）此前没有任何测试，
    把 `database._row_to_dict` 里的换算删掉，整个套件依然全绿。

    输入用显式 UTC 时间戳 2024-01-01 00:00:00，因此期望值唯一确定：
    2024-01-01T08:00:00+08:00。「贴标签式假修复」会把小时数留在 00，立刻露馅。
    """
    task_factory("dddd00000001", "时区探针", created_at="2024-01-01 00:00:00")

    payload = client.get("/api/tasks").json()

    assert payload[0]["created_at"] == "2024-01-01T08:00:00+08:00", (
        f"UTC 00:00 应换算为北京时间 08:00，实际 {payload[0]['created_at']!r}"
    )


# ============================================================
# PATCH /api/tasks/{task_id}/title
# ============================================================

def test_rename_task_persists_new_title(client, seeded_task):
    """200 + `{ok, title}`，且改完能从列表回读到新标题（真落库，不是只回显）。"""
    resp = client.patch(f"/api/tasks/{seeded_task}/title", json={"title": "三体"})

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert resp.json() == {"ok": True, "title": "三体"}, f"got {resp.json()}"

    assert _task_by_id(client, seeded_task)["title"] == "三体"


def test_rename_task_trims_surrounding_whitespace(client, seeded_task):
    """路由内部做了 `.strip()`——这条行为也要固定，否则前端保存会存入带空白的标题。"""
    resp = client.patch(f"/api/tasks/{seeded_task}/title", json={"title": "  三体  "})

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert resp.json()["title"] == "三体", f"got {resp.json()['title']!r}"


def test_rename_task_returns_404_for_unknown_task(client):
    """任务不存在 → 404（标题合法，因此走到存在性检查）。"""
    resp = client.patch("/api/tasks/nope/title", json={"title": "三体"})

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert resp.json()["detail"] == "任务不存在"


@pytest.mark.parametrize(
    "payload, case",
    [
        ({}, "完全没有 title 键"),
        ({"title": ""}, "空字符串"),
        ({"title": "   "}, "只有空白（strip 后为空）"),
    ],
    ids=["missing-key", "empty-string", "whitespace-only"],
)
def test_rename_task_rejects_blank_title(client, seeded_task, payload, case):
    """
    空白标题必须 422。

    ⚠️ 这里的 `detail` 是**字符串**，不是 FastAPI 校验层那种 `list`。
    与下面 `test_update_screenplay_rejects_non_object_screenplay` 形成直接对照。
    """
    resp = client.patch(f"/api/tasks/{seeded_task}/title", json=payload)

    assert resp.status_code == 422, f"{case}: got {resp.status_code}"
    assert resp.json()["detail"] == "Title cannot be empty", f"{case}: got {resp.json()}"


# ============================================================
# DELETE /api/tasks/{task_id}
# ============================================================

def test_delete_task_removes_it_from_list(client, seeded_task):
    """真删：删除后列表条数减一——这是抓「返回 200 但没删」的唯一手段。"""
    before = len(client.get("/api/tasks").json())

    resp = client.delete(f"/api/tasks/{seeded_task}")

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert resp.json() == {"ok": True}, f"got {resp.json()}"

    after = client.get("/api/tasks").json()
    assert len(after) == before - 1, f"条数没变：{before} → {len(after)}"
    assert seeded_task not in {t["task_id"] for t in after}


def test_delete_task_returns_404_for_unknown_task(client):
    resp = client.delete("/api/tasks/never-existed")

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert resp.json()["detail"] == "任务不存在"


def test_delete_task_twice_second_call_returns_404(client, seeded_task):
    """删除不幂等：第二次必须 404，而不是默默 200——否则前端的「删除成功」不可信。"""
    assert client.delete(f"/api/tasks/{seeded_task}").status_code == 200

    resp = client.delete(f"/api/tasks/{seeded_task}")

    assert resp.status_code == 404, f"第二次删除 got {resp.status_code}"


# ============================================================
# PATCH /api/screenplay/{task_id}
# ============================================================

def test_update_screenplay_persists_and_is_readable(client, completed_task):
    """改完的剧本要能从 GET /api/screenplay 读回来，且其余字段原样保留。"""
    updated = make_valid_screenplay_dict(title="改动后的标题")

    resp = client.patch(f"/api/screenplay/{completed_task}", json={"screenplay": updated})

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert resp.json() == {"ok": True}, f"got {resp.json()}"

    read_back = client.get(f"/api/screenplay/{completed_task}")
    assert read_back.status_code == 200, read_back.text

    body = read_back.json()
    assert body["meta"]["title"] == "改动后的标题", f"got {body['meta']['title']!r}"
    assert len(body["scenes"]) == len(updated["scenes"]), "场景列表被意外改动"


def test_update_screenplay_does_not_touch_task_title(client, completed_task):
    """剧本编辑只应写 result_json，不该顺手改任务名（职责边界）。"""
    original = _task_by_id(client, completed_task)["title"]

    client.patch(f"/api/screenplay/{completed_task}",
                 json={"screenplay": make_valid_screenplay_dict(title="另一个标题")})

    assert _task_by_id(client, completed_task)["title"] == original, "任务名被越界改动了"


def test_update_screenplay_returns_404_for_unknown_task(client):
    resp = client.patch("/api/screenplay/never-existed",
                        json={"screenplay": make_valid_screenplay_dict()})

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert resp.json()["detail"] == "任务不存在"


@pytest.mark.parametrize(
    "payload, case",
    [
        ({}, "缺少 screenplay 键"),
        ({"screenplay": "not-a-dict"}, "传字符串"),
        ({"screenplay": []}, "传数组"),
    ],
    ids=["missing-key", "string", "list"],
)
def test_update_screenplay_rejects_non_object_screenplay(client, completed_task, payload, case):
    """`ScreenplayUpdate.screenplay: dict` 只保证「是个 JSON 对象」，非对象必须被拦下。"""
    resp = client.patch(f"/api/screenplay/{completed_task}", json=payload)

    assert resp.status_code == 422, f"{case}: got {resp.status_code}"
    assert isinstance(resp.json()["detail"], list), f"{case}: got {resp.json()['detail']!r}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（PR 08 发现）：路由只校验 body.screenplay 是 JSON 对象，不做 Screenplay "
        "schema 校验，因此结构完全错误的剧本会拿到 200 并被原样落库；其后 "
        "GET /api/screenplay 与 4 个导出端点都会基于这份损坏数据产出垃圾，"
        "而任务历史里没有任何东西提示它已经坏了。"
        "计划书 PR 08 原本写「非法剧本结构 → 422」，实测为 200——"
        "本用例固化**期望行为**；修复后它会 XPASS，strict 模式下即失败，从而强制移除本标记。"
    ),
)
def test_update_screenplay_rejects_structurally_invalid_screenplay(client, completed_task):
    resp = client.patch(
        f"/api/screenplay/{completed_task}", json={"screenplay": {"garbage": True}}
    )

    assert resp.status_code == 422, f"got {resp.status_code}（结构错误的剧本被接受了）"


# ============================================================
# 辅助
# ============================================================

def _task_by_id(client, task_id: str) -> dict:
    """没有 GET /api/tasks/{id}，因此从列表里筛。"""
    for task in client.get("/api/tasks").json():
        if task["task_id"] == task_id:
            return task
    raise AssertionError(f"任务 {task_id} 不在列表中")
