import React, { useEffect, useState, useMemo } from "react";
import {
  CaretUpDown,
  CaretUp,
  CaretDown,
  Copy,
  Check,
  ArrowSquareOut,
} from "@phosphor-icons/react";
import { api, downloadUrl } from "@/lib/api";
import { ageDays, ageLabel } from "@/lib/readiness";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

const IMG = /\.(png|jpe?g|gif|webp|svg)$/i;
const TEXT = /\.(json|txt|csv|log|ya?ml|xml|md|html?)$/i;

// Integrity states reuse the status tokens so the vocabulary matches everywhere else.
const INTEGRITY = {
  ok: "bg-status-satisfied-bg text-status-satisfied",
  tampered: "bg-status-failed-bg text-status-failed",
  missing: "bg-status-failed-bg text-status-failed",
};
const INTEGRITY_LABEL = { ok: "Intact", tampered: "Tampered", missing: "Missing" };

function HashCell({ sha }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-xs text-muted-foreground">{sha.slice(0, 12)}…</span>
      <button
        type="button"
        aria-label="Copy full SHA-256"
        title={sha}
        onClick={async (e) => {
          e.stopPropagation();
          try {
            await navigator.clipboard.writeText(sha);
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          } catch { /* clipboard blocked — the title attribute still shows the full hash */ }
        }}
        className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        {copied ? <Check size={12} weight="bold" /> : <Copy size={12} />}
      </button>
    </div>
  );
}

function SortHead({ label, col, sort, onSort, className }) {
  const active = sort.key === col;
  const Icon = !active ? CaretUpDown : sort.dir === "asc" ? CaretUp : CaretDown;
  return (
    <TableHead className={className}>
      <button
        type="button"
        onClick={() => onSort(col)}
        className="inline-flex items-center gap-1 font-medium tracking-wide uppercase transition-colors hover:text-foreground"
      >
        {label}
        <Icon size={11} weight="bold" className={active ? "text-foreground" : "opacity-40"} aria-hidden />
      </button>
    </TableHead>
  );
}

export default function Evidence() {
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");
  const [integrity, setIntegrity] = useState({}); // id -> "ok"|"tampered"|"missing"
  const [verifying, setVerifying] = useState(false);
  const [preview, setPreview] = useState(null);
  const [sort, setSort] = useState({ key: "collected_at", dir: "desc" });

  useEffect(() => { api("/evidence").then(setItems).catch(() => setItems([])); }, []);

  const verifyAll = async () => {
    setVerifying(true);
    const r = await api("/integrity").catch(() => null);
    setVerifying(false);
    if (r && r.items) setIntegrity(Object.fromEntries(r.items.map((i) => [i.id, i.state])));
  };

  const onSort = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));

  const visible = useMemo(() => {
    if (!items) return [];
    const ql = q.toLowerCase();
    const filtered = items.filter(
      (e) => !ql || `${e.filename} ${e.control_code}`.toLowerCase().includes(ql)
    );
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sort.key === "collected_at") return (new Date(a.collected_at) - new Date(b.collected_at)) * dir;
      return String(a[sort.key]).localeCompare(String(b[sort.key])) * dir;
    });
  }, [items, q, sort]);

  if (items === null) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full max-w-md" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="grid place-items-center rounded-xl border border-dashed border-input bg-card px-6 py-14 text-center">
        <div className="max-w-sm">
          <h2 className="text-base font-semibold">No evidence yet</h2>
          <p className="mt-1.5 text-sm text-pretty text-muted-foreground">
            Run a collector against a control. Collected artifacts appear here — searchable, hashed, and traceable.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search evidence by filename or control…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="h-9 min-w-[200px] flex-1"
          aria-label="Search evidence"
        />
        <Button variant="outline" onClick={verifyAll} disabled={verifying}>
          {verifying ? "Verifying…" : "Verify all"}
        </Button>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="hover:bg-transparent">
              <SortHead label="File" col="filename" sort={sort} onSort={onSort} />
              <SortHead label="Control" col="control_code" sort={sort} onSort={onSort} />
              <SortHead label="Collected" col="collected_at" sort={sort} onSort={onSort} />
              <TableHead>SHA-256</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Integrity</TableHead>
              <TableHead className="w-px" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((e) => {
              const st = integrity[e.id];
              return (
                <TableRow key={e.id}>
                  <TableCell className="max-w-[22rem]">
                    <button
                      type="button"
                      onClick={() => setPreview(e)}
                      className="truncate text-left font-medium transition-colors hover:text-primary hover:underline"
                    >
                      {e.filename}
                    </button>
                  </TableCell>
                  <TableCell>
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      {e.control_code}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {ageLabel(ageDays(e.collected_at))}
                  </TableCell>
                  <TableCell><HashCell sha={e.sha256} /></TableCell>
                  <TableCell>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        e.sample
                          ? "bg-status-gap-bg text-status-gap"
                          : "bg-status-satisfied-bg text-status-satisfied"
                      }`}
                    >
                      {e.sample ? "Sample" : "Live"}
                    </span>
                  </TableCell>
                  <TableCell>
                    {st ? (
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${INTEGRITY[st] ?? ""}`}>
                        {INTEGRITY_LABEL[st] ?? st}
                      </span>
                    ) : (
                      <span className="text-sm text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <a
                      href={downloadUrl(e.id)}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Download ${e.filename}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                    >
                      Download
                      <ArrowSquareOut size={12} aria-hidden />
                    </a>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {visible.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-muted-foreground">
            No evidence matches “{q}”.
          </p>
        )}
      </div>

      {preview && <PreviewModal item={preview} onClose={() => setPreview(null)} />}
    </>
  );
}

/* ---------- inline preview ---------- */
function PreviewModal({ item, onClose }) {
  const [text, setText] = useState(null); // null=loading, false=not previewable, string=content
  const url = downloadUrl(item.id);
  const isImg = IMG.test(item.filename);

  useEffect(() => {
    if (isImg) { setText(false); return; }
    if (!TEXT.test(item.filename)) { setText(false); return; }
    let alive = true;
    fetch(url).then((r) => r.text()).then((t) => { if (alive) setText(t); }).catch(() => alive && setText(""));
    return () => { alive = false; };
  }, [item.id]);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="truncate">{item.filename}</DialogTitle>
          <DialogDescription className="font-mono">{item.control_code}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] overflow-auto rounded-lg border border-border bg-muted/30 p-3">
          {isImg ? (
            <img className="mx-auto block h-auto max-w-full rounded" src={url} alt={item.filename} />
          ) : text === null ? (
            <Skeleton className="h-40 w-full" />
          ) : text === false ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No inline preview for this file type — download to view.
            </p>
          ) : (
            <pre className="font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">{text}</pre>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" asChild>
            <a href={url} target="_blank" rel="noreferrer">Download</a>
          </Button>
          <Button onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
