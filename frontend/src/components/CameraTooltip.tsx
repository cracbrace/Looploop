const CAMERA_MOVEMENT_INFO: Record<string, { en: string; emotion: string; use: string }> = {
  "固定":    { en: "Static",     emotion: "冷静、观察、对峙", use: "需要稳定画面聚焦人物表情或对话时" },
  "推进":    { en: "Push In",    emotion: "关注、紧张升级、逼近感", use: "人物情绪逐渐激动或关键信息揭示时" },
  "拉远":    { en: "Pull Out",   emotion: "孤独、离别、渺小感", use: "人物独自离去或展现环境宏大时" },
  "左摇":    { en: "Pan Left",   emotion: "视线跟随、场景展开", use: "人物移动或展示横向空间时" },
  "右摇":    { en: "Pan Right",  emotion: "视线跟随、场景展开", use: "人物移动或展示横向空间时" },
  "上摇":    { en: "Tilt Up",    emotion: "仰视、崇高、权威感", use: "展现建筑高度或人物威严时" },
  "下摇":    { en: "Tilt Down",  emotion: "俯视、渺小、压迫感", use: "高空俯拍或人物被压制时" },
  "跟随":    { en: "Tracking",   emotion: "行进、追逐、代入感", use: "人物行走奔跑或跟拍动作时" },
  "环绕":    { en: "Arc",        emotion: "戏剧性、360°展示", use: "重要时刻需要全方位展现主体时" },
  "手持":    { en: "Handheld",   emotion: "紧张、纪实、混乱", use: "营造纪录片质感或混乱场景时" },
  "快速变焦": { en: "Crash Zoom", emotion: "震惊、反转、骤然关注", use: "信息突然揭示或情绪骤变时" },
};

interface CameraTooltipProps {
  movement: string;
  children: React.ReactNode;
}

export function CameraTooltip({ movement, children }: CameraTooltipProps) {
  const info = CAMERA_MOVEMENT_INFO[movement];
  if (!info) return <>{children}</>;

  return (
    <span className="relative group/tip inline-flex">
      {children}
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover/tip:block z-50">
        <span className="block w-48 bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl p-2 text-[10px] leading-relaxed text-zinc-300">
          <span className="font-semibold text-zinc-100">{movement}</span>
          <span className="text-zinc-500 ml-1">({info.en})</span>
          <div className="mt-1"><span className="text-zinc-500">情绪:</span> {info.emotion}</div>
          <div className="mt-0.5"><span className="text-zinc-500">使用:</span> {info.use}</div>
        </span>
        <span className="block w-2 h-2 bg-zinc-800 border-r border-b border-zinc-600 rotate-45 -mt-1 mx-auto" />
      </span>
    </span>
  );
}
