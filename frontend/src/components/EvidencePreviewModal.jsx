import React, { useEffect, useState, useMemo } from "react";
import {
  FileText,
  FilePdf,
  FileCode,
  FileImage,
  Table as TableIcon,
  File as FileGeneric,
  DownloadSimple,
  Copy,
  Check,
  ArrowSquareOut,
  ArrowsOut,
  ArrowsIn,
  MagnifyingGlass,
  Clock,
  ShieldCheck,
  Hash,
  X,
  Code,
  ListDashes,
} from "@phosphor-icons/react";
import { api, downloadUrl, previewUrl } from "@/lib/api";
import { ageDays, ageLabel } from "@/lib/readiness";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function getFileTypeInfo(filename = "") {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".pdf")) {
    return { type: "pdf", label: "PDF Document", icon: FilePdf, color: "text-red-500" };
  }
  if (lower.endsWith(".json")) {
    return { type: "json", label: "JSON Data", icon: FileCode, color: "text-amber-500" };
  }
  if (/\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(lower)) {
    return { type: "image", label: "Image / Screenshot", icon: FileImage, color: "text-blue-500" };
  }
  if (/\.(csv|tsv)$/i.test(lower)) {
    return { type: "table", label: "Tabular Data", icon: TableIcon, color: "text-emerald-500" };
  }
  if (/\.(ya?ml|xml|html?|sh|bash|py|js|ts|css)$/i.test(lower)) {
    return { type: "code", label: "Code / Config", icon: FileCode, color: "text-purple-500" };
  }
  if (/\.(txt|log|md|env)$/i.test(lower)) {
    return { type: "text", label: "Text Log", icon: FileText, color: "text-slate-500" };
  }
  return { type: "binary", label: "Binary File", icon: FileGeneric, color: "text-muted-foreground" };
}

// Simple syntax-colored JSON stringifier
function renderJsonWithSyntaxHighlight(jsonObj) {
  if (typeof jsonObj !== "string") {
    jsonObj = JSON.stringify(jsonObj, null, 2);
  }
  // Escape HTML characters
  const escaped = jsonObj
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\\-]?\d+)?)/g,
    (match) => {
      let cls = "text-amber-600 dark:text-amber-400"; // number
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          cls = "text-indigo-600 dark:text-indigo-400 font-semibold"; // key
        } else {
          cls = "text-emerald-600 dark:text-emerald-400"; // string
        }
      } else if (/true|false/.test(match)) {
        cls = "text-rose-600 dark:text-rose-400 font-medium"; // boolean
      } else if (/null/.test(match)) {
        cls = "text-muted-foreground italic"; // null
      }
      return `<span class="${cls}">${match}</span>`;
    }
  );
}

// Simple CSV parser for preview table
function parseCsv(content) {
  if (!content) return { headers: [], rows: [] };
  const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) return { headers: [], rows: [] };

  const parseLine = (line) => {
    const res = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"' && (i === 0 || line[i - 1] !== "\\")) {
        inQuotes = !inQuotes;
      } else if (c === "," && !inQuotes) {
        res.push(cur.trim().replace(/^"|"$/g, ""));
        cur = "";
      } else {
        cur += c;
      }
    }
    res.push(cur.trim().replace(/^"|"$/g, ""));
    return res;
  };

  const headers = parseLine(lines[0]);
  const rows = lines.slice(1, 101).map(parseLine); // limit preview to 100 rows
  return { headers, rows, totalRows: lines.length - 1 };
}

export default function EvidencePreviewModal({ evidence, onClose }) {
  const [detail, setDetail] = useState(evidence);
  const [content, setContent] = useState(null); // null = loading, string or object
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [hashCopied, setHashCopied] = useState(false);
  const [viewMode, setViewMode] = useState("default"); // 'default', 'raw', 'table'
  const [filterQuery, setFilterQuery] = useState("");
  const [imageZoom, setImageZoom] = useState(false);
  const [imageMeta, setImageMeta] = useState(null);

  const fileInfo = useMemo(() => getFileTypeInfo(detail?.filename), [detail?.filename]);
  const urlDownload = detail?.id ? downloadUrl(detail.id) : "#";
  const urlPreview = detail?.id ? previewUrl(detail.id) : "#";

  // Fetch full details if not already complete
  useEffect(() => {
    if (!evidence?.id) return;
    api(`/evidence/${evidence.id}`)
      .then((d) => setDetail((prev) => ({ ...prev, ...d })))
      .catch(() => {});
  }, [evidence?.id]);

  // Load preview content for text/code/json/csv
  useEffect(() => {
    if (!evidence?.id) return;
    const { type } = fileInfo;
    if (type === "pdf" || type === "image" || type === "binary") {
      setContent(true); // ready to display iframe or img
      return;
    }

    let alive = true;
    setContent(null);
    setError(null);

    fetch(urlPreview)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        return res.text();
      })
      .then((text) => {
        if (!alive) return;
        if (type === "json") {
          try {
            const parsed = JSON.parse(text);
            setContent({ raw: text, parsed });
          } catch {
            setContent({ raw: text, parsed: null });
          }
        } else {
          setContent(text);
        }
      })
      .catch((err) => {
        if (alive) {
          setError(err.message || "Failed to load file preview");
        }
      });

    return () => {
      alive = false;
    };
  }, [evidence?.id, fileInfo.type, urlPreview]);

  const handleCopyContent = async () => {
    let textToCopy = "";
    if (typeof content === "string") textToCopy = content;
    else if (content?.raw) textToCopy = content.raw;
    else if (content?.parsed) textToCopy = JSON.stringify(content.parsed, null, 2);

    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  const handleCopyHash = async (e) => {
    e?.stopPropagation();
    if (!detail?.sha256) return;
    try {
      await navigator.clipboard.writeText(detail.sha256);
      setHashCopied(true);
      setTimeout(() => setHashCopied(false), 1500);
    } catch {}
  };

  const IconComponent = fileInfo.icon;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-4xl max-h-[92vh] flex flex-col p-0 gap-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="p-4 sm:p-5 border-b border-border bg-card/60 backdrop-blur-sm shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pr-8">
            <div className="flex items-center gap-3 min-w-0">
              <div className={`p-2 rounded-lg bg-muted border border-border shrink-0 ${fileInfo.color}`}>
                <IconComponent size={22} weight="duotone" />
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-base sm:text-lg font-semibold truncate tracking-tight text-foreground" title={detail?.filename}>
                  {detail?.filename || "Evidence Preview"}
                </DialogTitle>
                <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-muted-foreground">
                  {detail?.control_code && (
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono font-medium text-foreground">
                      {detail.control_code}
                    </span>
                  )}
                  {detail?.control_name && (
                    <span className="truncate max-w-[200px]" title={detail.control_name}>
                      {detail.control_name}
                    </span>
                  )}
                  <span>•</span>
                  <span>{fileInfo.label}</span>
                  {detail?.size_bytes ? (
                    <>
                      <span>•</span>
                      <span>{formatBytes(detail.size_bytes)}</span>
                    </>
                  ) : null}
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      detail?.sample
                        ? "bg-status-gap-bg text-status-gap"
                        : "bg-status-satisfied-bg text-status-satisfied"
                    }`}
                  >
                    {detail?.sample ? "Sample" : "Live"}
                  </span>
                </div>
              </div>
            </div>

            {/* Quick action buttons */}
            <div className="flex items-center gap-1.5 self-end sm:self-center shrink-0">
              {(content?.raw || typeof content === "string") && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyContent}
                  className="h-8 gap-1.5 text-xs font-medium"
                  title="Copy full content to clipboard"
                >
                  {copied ? <Check size={14} className="text-status-satisfied" weight="bold" /> : <Copy size={14} />}
                  <span>{copied ? "Copied" : "Copy"}</span>
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                asChild
                className="h-8 gap-1.5 text-xs font-medium"
                title="Open directly in a new browser tab"
              >
                <a href={urlPreview} target="_blank" rel="noreferrer">
                  <ArrowSquareOut size={14} />
                  <span>Open tab</span>
                </a>
              </Button>
              <Button
                size="sm"
                asChild
                className="h-8 gap-1.5 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90"
                title="Download this evidence file"
              >
                <a href={urlDownload} target="_blank" rel="noreferrer" download={detail?.filename}>
                  <DownloadSimple size={14} weight="bold" />
                  <span>Download</span>
                </a>
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* Metadata Banner */}
        <div className="bg-muted/30 border-b border-border px-4 py-2 sm:px-5 text-xs flex flex-wrap items-center justify-between gap-y-1.5 gap-x-4 shrink-0 text-muted-foreground">
          <div className="flex items-center gap-2 min-w-0">
            <span className="flex items-center gap-1 font-mono text-[11px] text-foreground">
              <Hash size={13} className="text-muted-foreground" />
              SHA-256:
            </span>
            <span className="font-mono truncate max-w-[180px] sm:max-w-[320px]" title={detail?.sha256}>
              {detail?.sha256 || "—"}
            </span>
            {detail?.sha256 && (
              <button
                type="button"
                onClick={handleCopyHash}
                title="Copy SHA-256 hash"
                className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {hashCopied ? <Check size={12} weight="bold" className="text-status-satisfied" /> : <Copy size={12} />}
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {detail?.collected_at && (
              <span className="flex items-center gap-1">
                <Clock size={13} />
                <span>
                  {new Date(detail.collected_at).toLocaleDateString()} ({ageLabel(ageDays(detail.collected_at))})
                </span>
              </span>
            )}
            {detail?.meta?.url && (
              <span className="truncate max-w-[220px] text-muted-foreground" title={detail.meta.url}>
                URL: <span className="font-mono text-foreground">{detail.meta.url}</span>
              </span>
            )}
          </div>
        </div>

        {/* Format Specific Controls / Toggles */}
        {fileInfo.type === "json" && content?.parsed && (
          <div className="px-4 py-2 bg-card border-b border-border flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center gap-1">
              <Button
                variant={viewMode !== "raw" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setViewMode("default")}
                className="h-7 text-xs gap-1 px-2.5"
              >
                <Code size={13} />
                Formatted
              </Button>
              <Button
                variant={viewMode === "raw" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setViewMode("raw")}
                className="h-7 text-xs gap-1 px-2.5"
              >
                <ListDashes size={13} />
                Raw Text
              </Button>
            </div>
            <div className="relative w-48 sm:w-64">
              <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Filter keys or values…"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                className="h-7 w-full rounded-md border border-input bg-transparent pl-7 pr-2 text-xs outline-none focus:border-ring focus:ring-1 focus:ring-ring"
              />
              {filterQuery && (
                <button
                  type="button"
                  onClick={() => setFilterQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
        )}

        {fileInfo.type === "table" && typeof content === "string" && (
          <div className="px-4 py-2 bg-card border-b border-border flex items-center gap-1 shrink-0">
            <Button
              variant={viewMode !== "raw" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("default")}
              className="h-7 text-xs gap-1 px-2.5"
            >
              <TableIcon size={13} />
              Data Table
            </Button>
            <Button
              variant={viewMode === "raw" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("raw")}
              className="h-7 text-xs gap-1 px-2.5"
            >
              <ListDashes size={13} />
              Raw CSV
            </Button>
          </div>
        )}

        {fileInfo.type === "image" && (
          <div className="px-4 py-2 bg-card border-b border-border flex items-center justify-between text-xs text-muted-foreground shrink-0">
            <span>
              {imageMeta ? `${imageMeta.width} × ${imageMeta.height} px` : "Image Preview"}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setImageZoom(!imageZoom)}
              className="h-7 text-xs gap-1 px-2.5"
            >
              {imageZoom ? <ArrowsIn size={13} /> : <ArrowsOut size={13} />}
              <span>{imageZoom ? "Fit View" : "Original 100%"}</span>
            </Button>
          </div>
        )}

        {/* Content Viewer Area */}
        <div className="flex-1 overflow-auto bg-muted/20 p-3 sm:p-5 min-h-[320px] max-h-[64vh]">
          {error ? (
            <div className="h-full flex flex-col items-center justify-center py-12 text-center">
              <div className="rounded-full bg-destructive/10 p-3 text-destructive mb-3">
                <FileGeneric size={24} />
              </div>
              <h3 className="font-semibold text-sm">Failed to render preview</h3>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm">{error}</p>
              <Button size="sm" asChild className="mt-4 gap-1.5">
                <a href={urlDownload} target="_blank" rel="noreferrer">
                  <DownloadSimple size={14} />
                  Download File
                </a>
              </Button>
            </div>
          ) : content === null ? (
            <div className="space-y-3 py-6">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-20 w-5/6" />
            </div>
          ) : fileInfo.type === "pdf" ? (
            /* Native PDF embed iframe */
            <div className="w-full h-[62vh] rounded-lg overflow-hidden border border-border bg-white shadow-inner flex flex-col">
              <iframe
                src={urlPreview}
                title={detail?.filename}
                className="w-full h-full border-0"
              />
            </div>
          ) : fileInfo.type === "image" ? (
            /* Image viewer with zoom */
            <div className="w-full min-h-[300px] flex items-center justify-center p-4 rounded-lg border border-border bg-card/40 overflow-auto">
              <img
                src={urlPreview}
                alt={detail?.filename}
                onLoad={(e) => {
                  setImageMeta({
                    width: e.target.naturalWidth,
                    height: e.target.naturalHeight,
                  });
                }}
                className={`rounded shadow-sm transition-all duration-200 ${
                  imageZoom ? "max-w-none h-auto" : "max-h-[58vh] max-w-full h-auto object-contain"
                }`}
              />
            </div>
          ) : fileInfo.type === "json" ? (
            /* JSON viewer */
            viewMode === "raw" ? (
              <pre className="p-4 rounded-lg border border-border bg-card font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap break-all select-text">
                {content?.raw || ""}
              </pre>
            ) : (
              <div className="p-4 rounded-lg border border-border bg-card font-mono text-xs leading-relaxed overflow-x-auto select-text shadow-xs">
                {filterQuery ? (
                  // Simple filtered view
                  <pre className="whitespace-pre-wrap break-all">
                    {content?.raw
                      ?.split("\n")
                      .filter((line) => line.toLowerCase().includes(filterQuery.toLowerCase()))
                      .join("\n") || "No matching lines found."}
                  </pre>
                ) : (
                  <div
                    dangerouslySetInnerHTML={{
                      __html: renderJsonWithSyntaxHighlight(content?.parsed || content?.raw || {}),
                    }}
                  />
                )}
              </div>
            )
          ) : fileInfo.type === "table" ? (
            /* CSV Table viewer */
            viewMode === "raw" ? (
              <pre className="p-4 rounded-lg border border-border bg-card font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap break-all select-text">
                {content}
              </pre>
            ) : (
              (() => {
                const { headers, rows, totalRows } = parseCsv(content);
                return (
                  <div className="rounded-lg border border-border bg-card overflow-hidden shadow-xs">
                    <div className="overflow-x-auto max-h-[55vh]">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-muted/70 sticky top-0 border-b border-border text-foreground font-semibold">
                          <tr>
                            <th className="py-2 px-3 w-10 text-muted-foreground border-r border-border/50 text-center">#</th>
                            {headers.map((h, i) => (
                              <th key={i} className="py-2 px-3 border-r border-border/50 whitespace-nowrap">
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50 font-mono">
                          {rows.map((row, ri) => (
                            <tr key={ri} className="hover:bg-muted/40 transition-colors">
                              <td className="py-1.5 px-3 text-muted-foreground border-r border-border/50 text-center font-sans text-[11px]">
                                {ri + 1}
                              </td>
                              {headers.map((_, ci) => (
                                <td key={ci} className="py-1.5 px-3 border-r border-border/50 whitespace-nowrap text-foreground">
                                  {row[ci] ?? ""}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {totalRows > rows.length && (
                      <div className="p-2 text-center text-xs text-muted-foreground border-t border-border bg-muted/20">
                        Showing first {rows.length} of {totalRows} rows. Download full file to view all data.
                      </div>
                    )}
                  </div>
                );
              })()
            )
          ) : fileInfo.type === "text" || fileInfo.type === "code" ? (
            /* Monospace text viewer with line numbers */
            <div className="rounded-lg border border-border bg-card overflow-hidden shadow-xs">
              <div className="overflow-x-auto max-h-[58vh] p-3 font-mono text-xs leading-relaxed select-text">
                <pre className="whitespace-pre-wrap break-all text-foreground">
                  {content}
                </pre>
              </div>
            </div>
          ) : (
            /* Fallback binary viewer */
            <div className="h-full flex flex-col items-center justify-center py-12 text-center">
              <div className="rounded-full bg-muted p-4 text-muted-foreground mb-3 border border-border">
                <FileGeneric size={32} />
              </div>
              <h3 className="font-semibold text-base">{detail?.filename}</h3>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                Inline preview is not available for this binary format. You can download the file to inspect it locally.
              </p>
              <div className="mt-5 flex gap-2">
                <Button size="sm" asChild className="gap-1.5">
                  <a href={urlDownload} target="_blank" rel="noreferrer" download={detail?.filename}>
                    <DownloadSimple size={14} weight="bold" />
                    Download File ({formatBytes(detail?.size_bytes)})
                  </a>
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="p-3 sm:p-4 border-t border-border bg-card/60 backdrop-blur-sm flex items-center justify-between sm:justify-between shrink-0">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck size={14} className="text-status-satisfied" weight="bold" />
            <span>Cryptographically sealed & audit verifiable</span>
          </div>
          <Button variant="outline" size="sm" onClick={onClose} className="px-4">
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
