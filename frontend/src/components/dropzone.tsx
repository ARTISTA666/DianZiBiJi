"use client";

import { useCallback, useState, useRef } from "react";

interface DropzoneProps {
  onFilesSelected: (files: File[]) => void;
  accept?: string;
  maxSize?: number;
  multiple?: boolean;
  children?: React.ReactNode;
}

export function Dropzone({
  onFilesSelected,
  accept,
  maxSize,
  multiple = true,
  children,
}: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files);
      const filtered = maxSize ? files.filter((f) => f.size <= maxSize) : files;
      onFilesSelected(filtered);
    },
    [onFilesSelected, maxSize],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleClick = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      const filtered = maxSize ? files.filter((f) => f.size <= maxSize) : files;
      onFilesSelected(filtered);
      // Reset so the same file can be selected again
      e.target.value = "";
    },
    [onFilesSelected, maxSize],
  );

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={handleClick}
      className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
        isDragging
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-primary/50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        aria-label="选择上传文件"
        accept={accept}
        multiple={multiple}
        className="hidden"
        onChange={handleChange}
      />
      {children ?? (
        <div>
          <p className="text-sm">拖拽文件到此处，或点击选择文件</p>
          {maxSize && (
            <p className="text-xs text-muted-foreground mt-1">
              最大 {Math.round(maxSize / 1024 / 1024)}MB
            </p>
          )}
        </div>
      )}
    </div>
  );
}
