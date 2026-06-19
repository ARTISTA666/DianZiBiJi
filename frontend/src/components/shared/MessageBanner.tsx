"use client";

interface MessageBannerProps {
  message: string;
  error: string;
}

export function MessageBanner({ message, error }: MessageBannerProps) {
  if (!message && !error) return null;
  return (
    <div className={`rounded-md border px-4 py-3 text-sm ${error ? "border-red-200 bg-red-50 text-red-700" : "border-green-200 bg-green-50 text-green-700"}`}>
      {error || message}
    </div>
  );
}
