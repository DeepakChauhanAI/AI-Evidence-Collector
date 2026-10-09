import React, { useState } from "react";
import { Eye, DownloadSimple } from "@phosphor-icons/react";
import { downloadUrl } from "@/lib/api";
import StatusBadge from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import EvidencePreviewModal from "@/components/EvidencePreviewModal";

// For each run, the prior run of the same binding — so we can flag evidence that
// hasn't changed since last collection (filename -> sha256). Config drift shows as "changed".
function priorHashes(runs) {
  const seen = {}; // binding_id -> {filename: sha} of the prior (older) run
  const prev = {}; // run.id -> prior run's hashes
  for (let i = runs.length - 1; i >= 0; i--) { // oldest-first so the prior run is already seen
    const r = runs[i];
    prev[r.id] = seen[r.binding_id];
    seen[r.binding_id] = Object.fromEntries(r.evidence.map((e) => [e.filename, e.sha256]));
  }
  return prev;
}

const DIFF = {
  new: "bg-status-satisfied-bg text-status-satisfied",
  changed: "bg-status-gap-bg text-status-gap",
  unchanged: "bg-muted text-muted-foreground",
};

export default function Activity({ runs }) {
  const [previewEvidence, setPreviewEvidence] = useState(null);

  if (!runs.length) {
    return (
      <div className="grid place-items-center rounded-xl border border-dashed border-input bg-card px-6 py-14 text-center">
        <div className="max-w-sm">
          <h2 className="text-base font-semibold">No runs yet</h2>
          <p className="mt-1.5 text-sm text-pretty text-muted-foreground">
            Map a collector to a control and run it. Collected evidence appears here, hashed and timestamped.
          </p>
        </div>
      </div>
    );
  }

  const prev = priorHashes(runs);

  return (
    <>
      <div className="space-y-3">
        {runs.map((r) => (
          <Card key={r.id}>
            <CardContent className="pt-5">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-mono text-xs text-muted-foreground">
                  RUN-{String(r.id).padStart(4, "0")}
                </span>
                <StatusBadge
                  size="sm"
                  status={r.status === "success" ? "collected" : r.status === "error" ? "failed" : "pending"}
                />
                <span className="ml-auto text-sm text-muted-foreground">{r.message}</span>
              </div>

              {r.assessment && (
                <div
                  className={`mt-3 rounded-lg border p-3.5 ${
                    r.assessment.satisfied
                      ? "border-status-satisfied/30 bg-status-satisfied-bg"
                      : "border-status-gap/30 bg-status-gap-bg"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium">
                      {r.assessment.satisfied ? "Satisfies control" : "Gap found"}
                    </span>
                    <span className="text-xs text-muted-foreground tabular">
                      {Math.round(r.assessment.confidence * 100)}% confidence
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-pretty">{r.assessment.summary}</p>
                  {r.assessment.gaps && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">Gaps:</span> {r.assessment.gaps}
                    </p>
                  )}
                </div>
              )}

              {r.evidence.length > 0 && (
                <ul className="mt-3 space-y-1 border-t border-dashed border-border pt-3">
                  {r.evidence.map((e) => {
                    const before = prev[r.id] && prev[r.id][e.filename];
                    const diff = !before ? "new" : before === e.sha256 ? "unchanged" : "changed";
                    return (
                      <li
                        key={e.id}
                        className="flex items-center justify-between gap-2 rounded px-2 py-1.5 text-sm transition-colors hover:bg-muted/50 group"
                      >
                        <button
                          type="button"
                          onClick={() => setPreviewEvidence(e)}
                          className="flex items-center gap-2.5 min-w-0 flex-1 text-left transition-colors hover:text-primary"
                        >
                          <span className="min-w-0 truncate font-medium">{e.filename}</span>
                          {prev[r.id] && (
                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${DIFF[diff]}`}>
                              {diff}
                            </span>
                          )}
                          <span className="font-mono text-xs text-muted-foreground">
                            {e.sha256.slice(0, 12)}…
                          </span>
                        </button>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={() => setPreviewEvidence(e)}
                            className="p-1 rounded text-muted-foreground hover:text-primary transition-colors"
                            title={`Preview ${e.filename}`}
                            aria-label={`Preview ${e.filename}`}
                          >
                            <Eye size={14} />
                          </button>
                          <a
                            href={downloadUrl(e.id)}
                            target="_blank"
                            rel="noreferrer"
                            download={e.filename}
                            className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                            title={`Download ${e.filename}`}
                            aria-label={`Download ${e.filename}`}
                          >
                            <DownloadSimple size={14} />
                          </a>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {previewEvidence && (
        <EvidencePreviewModal
          evidence={previewEvidence}
          onClose={() => setPreviewEvidence(null)}
        />
      )}
    </>
  );
}
