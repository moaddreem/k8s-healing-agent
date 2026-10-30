// The report card: prints Nabd's steps line by line in plain words (with the technical detail
// underneath), asks for approval when needed, and stamps the result. Used on both pages.
import { fmt, type Step } from "./nabd";
import * as plain from "./plain";

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms: number) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));
const esc = (s: string) => s.replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[m]!);

export class Rx {
  private body: HTMLElement;
  private sign: HTMLElement;
  private status: HTMLElement;
  private printed = new Set<string>();

  constructor(private root: HTMLElement) {
    this.body = root.querySelector(".rx-body")!;
    this.sign = root.querySelector(".rx-sign")!;
    this.status = root.querySelector("[data-rx-status]")!;
  }

  private setStatus(text: string, tone: "idle" | "work" | "ok" | "warn") {
    this.status.textContent = text;
    this.status.dataset.tone = tone;
  }

  reset(message = "Nothing is broken yet. Pick a problem to start.") {
    this.printed.clear();
    this.body.innerHTML = `<p class="rx-empty">${esc(message)}</p>`;
    this.sign.hidden = true;
    this.setStatus("Waiting", "idle");
  }

  begin() {
    this.body.innerHTML = "";
    this.printed.clear();
    this.sign.hidden = true;
    this.setStatus("Working", "work");
  }

  async row(term: string, value: string, detail?: string, tone?: "ok" | "warn") {
    const dl = document.createElement("dl");
    dl.className = `rx-row print${tone ? " " + tone : ""}`;
    dl.innerHTML = `<dt>${esc(term)}</dt><dd>${esc(value)}${detail ? `<small>${esc(detail)}</small>` : ""}</dd>`;
    this.body.append(dl);
    await wait(170);
  }

  ask(): Promise<boolean> {
    this.sign.hidden = false;
    this.sign.dataset.state = "needed";
    this.setStatus("Waiting for you", "warn");
    this.sign.innerHTML =
      `<span>This changes how the app is set up. Approve it?</span>` +
      `<span class="actions"><button type="button" class="approve">Approve</button><button type="button" class="decline">Decline</button></span>`;
    this.sign.querySelector<HTMLButtonElement>(".approve")!.focus({ preventScroll: true });
    this.sign.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
    return new Promise((resolve) => {
      this.sign.querySelector(".approve")!.addEventListener("click", () => { this.done("You approved", "ok"); resolve(true); });
      this.sign.querySelector(".decline")!.addEventListener("click", () => { this.done("You declined", "warn"); resolve(false); });
    });
  }

  private done(text: string, tone: "ok" | "warn") {
    this.sign.dataset.state = "done";
    this.sign.innerHTML = `<span class="stamp ${tone}">${esc(text)}</span>`;
    this.setStatus("Working", "work");
  }

  private async final(text: string, tone: "ok" | "warn") {
    this.setStatus(text, tone);
    await wait(300);
  }

  // Translate one step of Nabd's loop into plain lines.
  async step(s: Step) {
    switch (s.kind) {
      case "detect":
        await this.row("Problem", plain.problem(s.lines), s.lines[0]);
        break;
      case "diagnose": {
        const f = s.finding!;
        if (this.printed.has(f.target)) break;
        this.printed.add(f.target);
        await this.row("Where", plain.where(f.target), f.target);
        await this.row("Cause", plain.cause(f), f.evidence[0]);
        break;
      }
      case "policy": {
        const f = s.finding!;
        await this.row("Fix", f.fix.map(plain.action).join(", then "), f.fix.map(fmt).join(" + "));
        const needs = s.lines.some((l) => l.includes("-> approve"));
        await this.row(
          "Approval",
          needs ? "Needed: this changes how the app is set up." : "Not needed: it's safe and can be undone.",
          undefined,
          needs ? "warn" : undefined,
        );
        break;
      }
      case "dryrun":
        await this.row(
          "Safety test",
          s.tone === "bad" ? "Failed: the system rejected the change." : "Passed: the system accepted the change before it was made.",
          undefined,
          s.tone === "bad" ? "warn" : undefined,
        );
        break;
      case "verify":
        if (s.tone === "ok") {
          await this.row("Result", "Fixed. The health check passes again.", undefined, "ok");
          await this.final("Fixed", "ok");
        } else await this.row("Result", "Not fixed yet, looking again.", undefined, "warn");
        break;
      case "rollback":
        await this.row("Undo", "Nabd undid its own change.", undefined, "warn");
        break;
      case "escalate":
        await this.row("Result", plain.reason(s.lines[0] ?? "", s.lines.join(" ")), undefined, "warn");
        await this.final("Handed to a human", "warn");
        break;
      case "healthy":
        await this.row("Result", "Nothing is broken.", undefined, "ok");
        break;
    }
  }
}
