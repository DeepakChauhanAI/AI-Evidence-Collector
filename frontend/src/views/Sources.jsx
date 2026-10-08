import React from "react";
import { BracketsCurly, FileText, Camera, Cloud, Robot } from "@phosphor-icons/react";
import { Card, CardContent } from "@/components/ui/card";

// One-line description + icon per collector type. Icons replace the text glyphs
// ("{ }", "DOC", "CAM", "AWS", "AI") that used to stand in for an icon set.
const META = {
  http_api: { icon: BracketsCurly, blurb: "Pulls JSON from any API — cloud, SaaS, or an internal endpoint." },
  document: { icon: FileText, blurb: "Fetches a document over HTTP — a policy PDF or exported report." },
  screenshot: { icon: Camera, blurb: "Captures a full-page screenshot of a console that has no API." },
  aws: { icon: Cloud, blurb: "Reads AWS configuration via boto3 (read-only). Falls back to a labeled sample without credentials." },
  agent: { icon: Robot, blurb: "Plans a collector and config from a natural-language goal, then delegates — the plan is recorded for audit." },
};

export default function Sources({ collectors, controls }) {
  // Derive, per collector, which controls it serves — the "few collectors, many controls" picture.
  const served = Object.fromEntries(collectors.map((c) => [c, []]));
  for (const ctrl of controls)
    for (const b of ctrl.bindings)
      if (served[b.collector_type]) served[b.collector_type].push(ctrl.code);

  return (
    <>
      <p className="mb-5 max-w-[70ch] border-l-2 border-primary pl-4 text-sm text-pretty text-muted-foreground">
        A small fleet of shared collectors serves every control. The same collector handles many
        controls — only its <span className="font-mono text-foreground">config</span> differs.
        Adding a control usually adds no code, just a mapping.
      </p>

      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-3">
        {collectors.map((c) => {
          const m = META[c] ?? { icon: BracketsCurly, blurb: "Evidence collector." };
          const Icon = m.icon;
          const codes = served[c] ?? [];
          return (
            <Card key={c} className="transition-shadow hover:shadow-e2">
              <CardContent className="pt-5">
                <div className="flex items-start gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <Icon size={20} weight="duotone" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{c}</span>
                      <span className="shrink-0 text-xs text-muted-foreground tabular">
                        {codes.length} control{codes.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-pretty text-muted-foreground">{m.blurb}</p>
                    {codes.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1">
                        {codes.map((code) => (
                          <span key={code} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                            {code}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}
