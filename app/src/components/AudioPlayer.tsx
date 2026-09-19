import { convertFileSrc } from "@tauri-apps/api/core";
import { useEffect, useRef } from "react";

interface Props {
  sourcePath: string | null;
  seekSeconds: number | null;
  onTimeUpdate?: (seconds: number) => void;
}

export function AudioPlayer({ sourcePath, seekSeconds, onTimeUpdate }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // 元数据加载前 currentTime 赋值会被忽略，先存下来等 loadedmetadata 再落。
  const pendingSeek = useRef<number | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || seekSeconds === null) return;
    if (audio.readyState >= 1) {
      audio.currentTime = seekSeconds;
    } else {
      pendingSeek.current = seekSeconds;
    }
  }, [seekSeconds]);

  if (!sourcePath) {
    return <section className="panel player empty">尚未载入音频</section>;
  }

  // webview 不允许直接读 file://，必须经 Tauri 的 asset 协议转换。
  // 中文和空格路径也能正确处理，不要自己拼 file:// 字符串。
  const src = convertFileSrc(sourcePath);

  return (
    <section className="panel player">
      <audio
        ref={audioRef}
        controls
        src={src}
        onLoadedMetadata={() => {
          const audio = audioRef.current;
          if (audio && pendingSeek.current !== null) {
            audio.currentTime = pendingSeek.current;
            pendingSeek.current = null;
          }
        }}
        onTimeUpdate={(event) => onTimeUpdate?.(event.currentTarget.currentTime)}
      />
    </section>
  );
}
