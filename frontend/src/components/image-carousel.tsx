"use client";

import { useState, useEffect, useRef, useCallback, KeyboardEvent, TouchEvent } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
  Download,
  Image as ImageIcon,
  AlertCircle,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface CarouselImage {
  id: string | number;
  url: string;
  title?: string;
  caption?: string;
  fileId?: number;
}

interface ImageCarouselProps {
  images: CarouselImage[];
  initialIndex?: number;
  className?: string;
  showThumbnails?: boolean;
  showCounter?: boolean;
  showControls?: boolean;
  aspectRatioClass?: string;
  onImageClick?: (image: CarouselImage, index: number) => void;
}

/**
 * 缓存已经加载完成的 Blob URL，避免每次切换重复下载
 */
const blobCache = new Map<string, string>();

export function ImageCarousel({
  images,
  initialIndex = 0,
  className,
  showThumbnails = true,
  showCounter = true,
  showControls = true,
  aspectRatioClass = "aspect-[16/10]",
  onImageClick,
}: ImageCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(
    Math.max(0, Math.min(initialIndex, images.length - 1))
  );
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [resolvedUrls, setResolvedUrls] = useState<Record<string, string>>({});
  const [loadingMap, setLoadingMap] = useState<Record<string, boolean>>({});
  const [errorMap, setErrorMap] = useState<Record<string, boolean>>({});

  // 触摸滑动记录
  const touchStartX = useRef<number | null>(null);
  const touchDeltaX = useRef<number>(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // 保证 currentIndex 在合理范围
  useEffect(() => {
    if (images.length === 0) {
      setCurrentIndex(0);
    } else if (currentIndex >= images.length) {
      setCurrentIndex(images.length - 1);
    }
  }, [images.length, currentIndex]);

  // 加载单张图片，若为后端受保护文件则带凭证获取 blob URL
  const loadImage = useCallback(async (img: CarouselImage) => {
    const key = String(img.id ?? img.url);
    if (blobCache.has(key)) {
      setResolvedUrls((prev) => ({ ...prev, [key]: blobCache.get(key)! }));
      setLoadingMap((prev) => ({ ...prev, [key]: false }));
      return;
    }

    setLoadingMap((prev) => ({ ...prev, [key]: true }));
    setErrorMap((prev) => ({ ...prev, [key]: false }));

    try {
      // 检查是否为同源或后端 download API
      if (img.url.includes("/files/") && img.url.includes("/download")) {
        const res = await fetch(img.url, { credentials: "include" });
        if (!res.ok) {
          throw new Error(`加载失败: ${res.status}`);
        }
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        blobCache.set(key, objectUrl);
        setResolvedUrls((prev) => ({ ...prev, [key]: objectUrl }));
      } else {
        // 普通 URL 直接使用
        setResolvedUrls((prev) => ({ ...prev, [key]: img.url }));
      }
    } catch {
      setErrorMap((prev) => ({ ...prev, [key]: true }));
    } finally {
      setLoadingMap((prev) => ({ ...prev, [key]: false }));
    }
  }, []);

  // 预加载当前图片以及前后相邻的图片
  useEffect(() => {
    if (images.length === 0) return;
    const current = images[currentIndex];
    if (current) loadImage(current);

    // 预加载前后相邻项
    const nextIdx = (currentIndex + 1) % images.length;
    const prevIdx = (currentIndex - 1 + images.length) % images.length;
    if (images[nextIdx]) loadImage(images[nextIdx]);
    if (images[prevIdx]) loadImage(images[prevIdx]);
  }, [currentIndex, images, loadImage]);

  const prevImage = useCallback(() => {
    if (images.length <= 1) return;
    setCurrentIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1));
  }, [images.length]);

  const nextImage = useCallback(() => {
    if (images.length <= 1) return;
    setCurrentIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1));
  }, [images.length]);

  // 键盘左右切换与 ESC 退出全屏
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement> | globalThis.KeyboardEvent) => {
      if (images.length <= 1 && !isFullscreen) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        prevImage();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        nextImage();
      } else if (e.key === "Escape" && isFullscreen) {
        e.preventDefault();
        setIsFullscreen(false);
      }
    },
    [images.length, isFullscreen, prevImage, nextImage]
  );

  // 全屏状态下监听全局键盘事件
  useEffect(() => {
    if (!isFullscreen) return;
    const onGlobalKeyDown = (e: globalThis.KeyboardEvent) => handleKeyDown(e);
    window.addEventListener("keydown", onGlobalKeyDown);
    return () => window.removeEventListener("keydown", onGlobalKeyDown);
  }, [isFullscreen, handleKeyDown]);

  // 触摸手势事件
  const handleTouchStart = (e: TouchEvent<HTMLDivElement>) => {
    if (e.touches.length === 1) {
      touchStartX.current = e.touches[0].clientX;
      touchDeltaX.current = 0;
    }
  };

  const handleTouchMove = (e: TouchEvent<HTMLDivElement>) => {
    if (touchStartX.current !== null && e.touches.length === 1) {
      touchDeltaX.current = e.touches[0].clientX - touchStartX.current;
    }
  };

  const handleTouchEnd = () => {
    if (touchStartX.current !== null) {
      const threshold = 40;
      if (touchDeltaX.current > threshold) {
        prevImage();
      } else if (touchDeltaX.current < -threshold) {
        nextImage();
      }
    }
    touchStartX.current = null;
    touchDeltaX.current = 0;
  };

  // 下载当前图片
  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    const current = images[currentIndex];
    if (!current) return;
    const key = String(current.id ?? current.url);
    const downloadUrl = resolvedUrls[key] || current.url;

    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = current.title || `image-${currentIndex + 1}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  if (!images || images.length === 0) {
    return null;
  }

  const currentImage = images[currentIndex];
  const currentKey = String(currentImage?.id ?? currentImage?.url ?? "");
  const currentUrl = resolvedUrls[currentKey] || currentImage?.url;
  const isLoading = loadingMap[currentKey];
  const isError = errorMap[currentKey];
  const hasMultiple = images.length > 1;

  // 轮播主要展示区域
  const mainViewer = (
    <div
      ref={containerRef}
      role="region"
      aria-label="图片画廊与左右轮播"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      className={cn(
        "group relative select-none overflow-hidden rounded-xl border border-border/80 bg-neutral-950/90 text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/60",
        isFullscreen ? "h-[85vh] w-full border-none rounded-none bg-black/95" : aspectRatioClass
      )}
    >
      {/* 居中图片渲染 */}
      <div
        className="flex h-full w-full items-center justify-center p-2 cursor-pointer"
        onClick={() => {
          if (onImageClick) {
            onImageClick(currentImage, currentIndex);
          } else {
            setIsFullscreen((prev) => !prev);
          }
        }}
      >
        {isLoading ? (
          <div className="flex flex-col items-center justify-center gap-2 text-neutral-400">
            <RefreshCw className="h-8 w-8 animate-spin text-primary" />
            <span className="text-xs">加载图片中...</span>
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center gap-2 text-rose-400">
            <AlertCircle className="h-8 w-8" />
            <span className="text-xs font-medium">图片加载失败</span>
            <Button
              variant="outline"
              size="sm"
              className="mt-1 h-7 text-xs bg-neutral-900 border-neutral-700 text-neutral-200 hover:bg-neutral-800"
              onClick={(e) => {
                e.stopPropagation();
                loadImage(currentImage);
              }}
            >
              <RefreshCw className="mr-1 h-3 w-3" /> 点击重试
            </Button>
          </div>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={currentUrl}
            alt={currentImage?.title || `图片 ${currentIndex + 1}`}
            className="max-h-full max-w-full object-contain transition-all duration-300 ease-out"
            draggable={false}
          />
        )}
      </div>

      {/* 顶部悬浮控制栏 */}
      <div className="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none">
        {/* 图片标题或指示 */}
        <div className="flex items-center gap-2 pointer-events-auto">
          {showCounter && hasMultiple && (
            <span className="inline-flex items-center gap-1 rounded-full bg-black/60 backdrop-blur-md px-2.5 py-1 text-xs font-medium text-white/90 shadow-sm border border-white/10">
              <ImageIcon className="h-3 w-3" />
              {currentIndex + 1} / {images.length}
            </span>
          )}
          {currentImage?.title && (
            <span className="max-w-[200px] sm:max-w-xs truncate rounded-full bg-black/60 backdrop-blur-md px-3 py-1 text-xs text-white/80 border border-white/10">
              {currentImage.title}
            </span>
          )}
        </div>

        {/* 顶部快捷操作 */}
        <div className="flex items-center gap-1.5 pointer-events-auto">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full bg-black/50 text-white/80 hover:bg-black/80 hover:text-white backdrop-blur-md"
            title="下载此图片"
            aria-label="下载此图片"
            onClick={handleDownload}
          >
            <Download className="h-4 w-4" />
          </Button>
          {currentUrl && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full bg-black/50 text-white/80 hover:bg-black/80 hover:text-white backdrop-blur-md"
              title="在新标签页打开"
              aria-label="在新标签页打开"
              onClick={(e) => {
                e.stopPropagation();
                window.open(currentUrl, "_blank");
              }}
            >
              <ExternalLink className="h-4 w-4" />
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full bg-black/50 text-white/80 hover:bg-black/80 hover:text-white backdrop-blur-md"
            title={isFullscreen ? "退出全屏" : "全屏放大查看"}
            aria-label={isFullscreen ? "退出全屏" : "全屏放大查看"}
            onClick={(e) => {
              e.stopPropagation();
              setIsFullscreen((prev) => !prev);
            }}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* 左右切换按钮（仅当有 2 张及以上图片时展示） */}
      {showControls && hasMultiple && (
        <>
          <button
            type="button"
            aria-label="查看上一张图片"
            onClick={(e) => {
              e.stopPropagation();
              prevImage();
            }}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 flex h-9 w-9 sm:h-10 sm:w-10 items-center justify-center rounded-full bg-black/45 text-white/90 shadow-md backdrop-blur-sm transition-all duration-200 hover:bg-black/80 hover:scale-105 active:scale-95 border border-white/10 group-hover:opacity-100 opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <ChevronLeft className="h-5 w-5 sm:h-6 sm:w-6" />
          </button>

          <button
            type="button"
            aria-label="查看下一张图片"
            onClick={(e) => {
              e.stopPropagation();
              nextImage();
            }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 flex h-9 w-9 sm:h-10 sm:w-10 items-center justify-center rounded-full bg-black/45 text-white/90 shadow-md backdrop-blur-sm transition-all duration-200 hover:bg-black/80 hover:scale-105 active:scale-95 border border-white/10 group-hover:opacity-100 opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <ChevronRight className="h-5 w-5 sm:h-6 sm:w-6" />
          </button>
        </>
      )}

      {/* 底部指示圆点（Dots Indicator） */}
      {hasMultiple && (
        <div className="absolute bottom-3 left-0 right-0 flex items-center justify-center gap-1.5 pointer-events-none">
          <div className="flex items-center gap-1.5 rounded-full bg-black/50 backdrop-blur-md px-2.5 py-1 pointer-events-auto border border-white/10">
            {images.map((img, idx) => (
              <button
                key={img.id ?? idx}
                type="button"
                aria-label={`跳转到图片 ${idx + 1}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setCurrentIndex(idx);
                }}
                className={cn(
                  "h-2 rounded-full transition-all duration-300 focus:outline-none",
                  idx === currentIndex
                    ? "w-5 bg-primary shadow-sm"
                    : "w-2 bg-white/40 hover:bg-white/70"
                )}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className={cn("space-y-2.5", className)}>
      {/* 主轮播展示区域 */}
      {mainViewer}

      {/* 缩略图横向滚动条（仅在非全屏且图片 > 1 张时展示） */}
      {showThumbnails && hasMultiple && !isFullscreen && (
        <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-thin scrollbar-thumb-muted">
          {images.map((img, idx) => {
            const thumbKey = String(img.id ?? img.url);
            const thumbUrl = resolvedUrls[thumbKey] || img.url;
            const isSelected = idx === currentIndex;

            return (
              <button
                key={img.id ?? idx}
                type="button"
                aria-label={`切换至缩略图 ${idx + 1}: ${img.title || ""}`}
                onClick={() => setCurrentIndex(idx)}
                className={cn(
                  "relative h-14 w-18 shrink-0 overflow-hidden rounded-lg border-2 transition-all duration-200 bg-neutral-900",
                  isSelected
                    ? "border-primary ring-2 ring-primary/40 shadow-sm scale-105"
                    : "border-border/60 opacity-65 hover:opacity-100 hover:border-foreground/30"
                )}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={thumbUrl}
                  alt={img.title || `缩略图 ${idx + 1}`}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
                <span className="absolute bottom-0 right-0 rounded-tl bg-black/70 px-1 text-[9px] font-mono text-white/90">
                  {idx + 1}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* 全屏 Modal 灯箱 */}
      {isFullscreen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="图片全屏放大查看"
          className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 backdrop-blur-md p-4 animate-in fade-in-0 duration-200"
          onClick={() => setIsFullscreen(false)}
        >
          <div
            className="relative flex flex-col items-center justify-center max-h-full max-w-5xl w-full"
            onClick={(e) => e.stopPropagation()}
          >
            {mainViewer}

            {/* 全屏底部的缩略图指示条 */}
            {hasMultiple && (
              <div className="mt-3 flex max-w-full items-center justify-center gap-2 overflow-x-auto py-1">
                {images.map((img, idx) => {
                  const thumbKey = String(img.id ?? img.url);
                  const thumbUrl = resolvedUrls[thumbKey] || img.url;
                  const isSelected = idx === currentIndex;

                  return (
                    <button
                      key={img.id ?? idx}
                      type="button"
                      aria-label={`切换至图片 ${idx + 1}`}
                      onClick={() => setCurrentIndex(idx)}
                      className={cn(
                        "h-12 w-16 shrink-0 overflow-hidden rounded-md border transition-all duration-150 bg-neutral-900",
                        isSelected
                          ? "border-primary ring-2 ring-primary/50 scale-105"
                          : "border-white/20 opacity-60 hover:opacity-100"
                      )}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={thumbUrl}
                        alt={img.title || `缩略图 ${idx + 1}`}
                        className="h-full w-full object-cover"
                      />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
