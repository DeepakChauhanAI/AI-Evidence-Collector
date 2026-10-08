import React, { useState } from "react";
import { Sparkle } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// Pre-filled config per collector so the operator starts from a working shape, not a blank box.
export const CONFIG_TEMPLATES = {
  http_api: { url: "https://api.example.com/compliance/export", method: "GET", headers: {} },
  document: { url: "https://intranet.example.com/policies/access-control.pdf" },
  screenshot: { url: "https://console.example.com/dashboard", full_page: true },
  aws: { service: "iam", operation: "get_account_password_policy", region: "us-east-1" },
  agent: { goal: "Collect evidence that MFA is enforced for all admin access." },
};

export default function BindModal({ control, collectors, onClose, onSaved, toast }) {
  const initial = control.suggested_collector || collectors[0] || "http_api";
  const [type, setType] = useState(initial);
  const [config, setConfig] = useState(JSON.stringify(CONFIG_TEMPLATES[initial] || {}, null, 2));
  const [minutes, setMinutes] = useState(0);
  const [busy, setBusy] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [configError, setConfigError] = useState("");

  const pick = (t) => {
    setType(t);
    setConfig(JSON.stringify(CONFIG_TEMPLATES[t] || {}, null, 2));
    setConfigError("");
  };

  const suggest = async () => {
    setSuggesting(true);
    const r = await api(`/controls/${control.id}/suggest-collector`, { method: "POST" }).catch(() => null);
    setSuggesting(false);
    if (r && r.collector_type) { pick(r.collector_type); toast(`AI suggests ${r.collector_type}.`); }
    else toast("AI suggestion unavailable.");
  };

  const draft = async () => {
    setDrafting(true);
    const r = await api(`/controls/${control.id}/draft-config?collector_type=${encodeURIComponent(type)}`, { method: "POST" }).catch(() => null);
    setDrafting(false);
    if (r && r.config && Object.keys(r.config).length) {
      setConfig(JSON.stringify(r.config, null, 2));
      setConfigError("");
      toast("Config drafted by AI.");
    } else {
      toast("AI draft unavailable — set AI_API_KEY, or edit the config by hand.");
    }
  };

  const save = async () => {
    let parsed;
    try {
      parsed = JSON.parse(config);
    } catch {
      // Inline, next to the field that is wrong — not just a toast that vanishes.
      setConfigError("That isn't valid JSON. Check the brackets and quotes.");
      return;
    }
    setConfigError("");
    setBusy(true);
    const r = await api("/bindings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ control_id: control.id, collector_type: type, config: parsed, schedule_minutes: Number(minutes) || 0 }),
    }).catch(() => null);
    setBusy(false);
    if (r && r.id) { onSaved(); onClose(); toast(`Collector mapped to ${control.code}.`); }
    else toast("Couldn't save the collector.");
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Map a collector</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{control.code}</span> · {control.name}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="collector">Collector</Label>
              <button
                type="button"
                onClick={suggest}
                disabled={suggesting}
                className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline disabled:opacity-50 disabled:no-underline"
              >
                <Sparkle size={12} weight="fill" aria-hidden />
                {suggesting ? "Thinking…" : "Suggest"}
              </button>
            </div>
            <Select value={type} onValueChange={pick}>
              <SelectTrigger id="collector" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {collectors.map((c) => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="config">
                Configuration <span className="font-normal text-muted-foreground">what to collect</span>
              </Label>
              <button
                type="button"
                onClick={draft}
                disabled={drafting}
                className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline disabled:opacity-50 disabled:no-underline"
              >
                <Sparkle size={12} weight="fill" aria-hidden />
                {drafting ? "Drafting…" : "Draft with AI"}
              </button>
            </div>
            <Textarea
              id="config"
              value={config}
              onChange={(e) => { setConfig(e.target.value); setConfigError(""); }}
              spellCheck={false}
              rows={6}
              aria-invalid={configError ? true : undefined}
              aria-describedby={configError ? "config-error" : undefined}
              className="font-mono text-xs"
            />
            {configError && (
              <p id="config-error" className="text-xs text-status-failed">
                {configError}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="schedule">
              Schedule <span className="font-normal text-muted-foreground">minutes between runs · 0 = manual</span>
            </Label>
            <Input
              id="schedule"
              type="number"
              min="0"
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={busy}>{busy ? "Saving…" : "Map collector"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
