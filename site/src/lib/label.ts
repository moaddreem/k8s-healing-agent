// The dispensing label: prints Nabd's steps line by line, asks for a countersignature,
// and stamps the outcome. Used by the landing hero and the demo page.
import { fmt, type Step } from "./nabd";

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms: number) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));

export class Rx {
  private body: HTMLElement;
  private sign: HTMLElement;
  private no: HTMLElement;
  private printed = new Set<string>();
  private count = 0;

  constructor(private root: HTMLElement) {
    this.body = root.querySelector(".rx-body")!;
    this.sign = root.querySelector(".rx-sign")!;
    this.no = root.querySelector("[data-rx-no]")!;
  }

  reset(message = "No patient waiting. Break something to start.") {
    this.printed.clear();
    this.body.innerHTML = `<p class="rx-empty">${message}</p>`;
    this.signState("idle", "Pharmacist countersign: not needed yet");
  }

  begin() {
    this.count++;
    this.no.textContent = `Rx ${String(this.count).padStart(4, "0")}`;
    this.body.innerHTML = "";
    this.printed.clear();
    this.signState("idle", "Pharmacist countersign: not needed yet");
  }

  async row(term: string, value: string, tone?: "ok" | "warn") {
    const dl = document.createElement("dl");
    dl.className = `rx-row print${tone ? " " + tone : ""}`;
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.append(dt, dd);
    this.body.append(dl);
    await wait(170);
  }

  private signState(state: "idle" | "needed" | "done", text: string) {
    this.sign.dataset.state = state;
    this.sign.innerHTML = `<span>${text}</span>`;
  }

  ask(): Promise<boolean> {
    this.sign.dataset.state = "needed";
    this.sign.innerHTML =
      `<span>Countersign required: this edits configuration</span>` +
      `<span class="actions"><button type="button" class="approve">Approve</button><button type="button" class="decline">Decline</button></span>`;
    this.sign.querySelector<HTMLButtonElement>(".approve")!.focus({ preventScroll: true });
    this.sign.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
    return new Promise((resolve) => {
      this.sign.querySelector(".approve")!.addEventListener("click", () => { this.stamp("Countersigned", "ok"); resolve(true); });
      this.sign.querySelector(".decline")!.addEventListener("click", () => { this.stamp("Declined", "warn"); resolve(false); });
    });
  }

  stamp(text: string, tone: "ok" | "warn") {
    this.sign.dataset.state = "done";
    this.sign.innerHTML = `<span>Pharmacist countersign</span><span class="stamp ${tone}">${text}</span>`;
  }

  async finalStamp(text: string, tone: "ok" | "warn") {
    const p = document.createElement("p");
    p.style.marginTop = "1rem";
    p.innerHTML = `<span class="stamp ${tone}">${text}</span>`;
    this.body.append(p);
    await wait(300);
  }

  // Translate one step of Nabd's loop into label lines.
  async step(s: Step) {
    switch (s.kind) {
      case "detect":
        await this.row("Complaint", s.lines[0] ?? "health check failing");
        break;
      case "diagnose": {
        const f = s.finding!;
        if (this.printed.has(f.target)) break;
        this.printed.add(f.target);
        await this.row("Patient", f.target);
        await this.row("Indication", f.summary);
        if (f.evidence[0]) await this.row("Evidence", f.evidence[0]);
        break;
      }
      case "group":
        await this.row("Grouped", s.lines[0]);
        break;
      case "policy": {
        const f = s.finding!;
        await this.row("Dispense", f.fix.map(fmt).join(" + "));
        const needs = s.lines.some((l) => l.includes("-> approve"));
        await this.row("Class", needs ? "countersign required (medium risk)" : "over the counter: runs automatically", needs ? "warn" : undefined);
        break;
      }
      case "dryrun":
        await this.row("Dry-run", s.lines[0].replace(/^.*?: /, ""), s.tone === "bad" ? "warn" : undefined);
        break;
      case "verify":
        if (s.tone === "ok") {
          await this.row("Outcome", s.lines[0], "ok");
          await this.finalStamp("Dispensed · healthy", "ok");
        } else await this.row("Follow-up", s.lines[0], "warn");
        break;
      case "rollback":
        await this.row("Rollback", `${s.title.replace("Roll back ", "")}: ${s.lines[0]}`, "warn");
        break;
      case "escalate":
        await this.row("Outcome", s.lines[0], "warn");
        await this.finalStamp("Refer to a human", "warn");
        break;
      case "healthy":
        await this.row("Outcome", "everything is healthy, nothing to dispense", "ok");
        break;
    }
  }
}
