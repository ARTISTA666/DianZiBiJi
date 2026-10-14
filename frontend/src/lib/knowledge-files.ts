// Keep the knowledge-document selector aligned with the backend extractor formats.
const imageExtensions = ["png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp"];
const textExtensions = ["txt", "csv", "tsv", "soft", "md", "json", "xml", "html", "log", "yaml", "yml"];
const extensions = ["pdf", ...imageExtensions, ...textExtensions, ...textExtensions.map((extension) => `${extension}.gz`)];
const mimeTypes = new Set([
  "application/pdf", "image/png", "image/jpeg", "image/gif", "image/bmp", "image/tiff", "image/webp",
  "text/plain", "text/csv", "text/tab-separated-values", "text/markdown", "application/json",
  "application/xml", "text/xml", "text/html", "text/yaml", "application/yaml", "application/x-yaml",
  "text/x-yaml", "application/gzip", "application/x-gzip", "application/octet-stream",
]);

export const KNOWLEDGE_DOCUMENT_ACCEPT = extensions.map((extension) => `.${extension}`).join(",");
export const NOTE_ATTACHMENT_ACCEPT = `${KNOWLEDGE_DOCUMENT_ACCEPT},.doc,.docx,.xls,.xlsx,.pptx`;

export function isSupportedKnowledgeFile(file: Pick<File, "name" | "type">) {
  const name = file.name.toLowerCase();
  // .docx.gz and bare .gz cannot pass via the generic gzip MIME.
  const supportedExtension = extensions.some((extension) => name.endsWith(`.${extension}`));
  return supportedExtension && mimeTypes.has(file.type.toLowerCase() || "application/octet-stream");
}
