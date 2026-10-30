// Plain-language wording for people who don't know Kubernetes. The technical detail is still shown,
// smaller, next to these sentences, so engineers lose nothing.
import type { Action, Finding } from "./nabd";

export const FAULT_NAME: Record<string, string> = {
  "dev-01-image-typo": "Typo in the app's version number",
  "dev-02-configmap-key-typo": "Typo in the name of a setting",
  "dev-03-oom": "Memory limit set too low",
  "dev-04-liveness-port": "Health check pointed at the wrong door",
  "dev-05-readiness-path": "Health check asks for a page that doesn't exist",
  "dev-06-selector-mismatch": "Traffic sent to a label nobody has",
  "dev-07-cpu-request": "Asked for 64 processors instead of a tiny slice",
  "dev-08-missing-secret": "A password was deleted",
  "dev-09-scaled-to-zero": "The app was switched off",
  "ho-01-target-port": "Traffic sent to the wrong door",
  "ho-02-bad-command": "Typo in the start command",
  "ho-03-node-selector": "Asked for a kind of server that doesn't exist",
  "ho-04-quota": "An admin limit blocks new copies",
  "ho-05-double-fault": "Two different faults at once",
};

export const APP_NAME: Record<string, string> = { web: "Website", api: "Data service", worker: "Background worker" };

export const CHECK_NAME: Record<string, string> = {
  "GET web /": "Website answers",
  "GET web /api/": "Website can reach the data service",
  "deploy/web": "Website copies running",
  "deploy/api": "Data service copies running",
  "deploy/worker": "Background worker running",
  "no restarting pods": "Nothing keeps crashing",
};

export function problem(lines: string[]): string {
  const has = (s: string) => lines.some((l) => l.includes(s));
  if (has("GET web / ")) return "The website doesn't answer.";
  if (has("GET web /api/")) return "Part of the website returns errors.";
  if (has("scaled to 0")) return "The app is switched off.";
  if (has("rollout not healthy")) return "An update to the app is stuck.";
  if (has("restarting")) return "The app keeps crashing and restarting.";
  return "Something is unhealthy.";
}

export function where(target: string): string {
  const [kind, name] = target.split("/");
  const app = APP_NAME[name] ?? name;
  if (kind === "deployment") return `The ${app.toLowerCase()}`;
  if (kind === "service") return `The ${app.toLowerCase()}'s address`;
  if (kind === "configmap") return "The data service's settings";
  return target;
}

export function cause(f: Finding): string {
  switch (f.rule) {
    case "scaled_to_zero":
      return "Someone switched it off: zero copies are running.";
    case "missing_reference":
      return "A password it needs was deleted.";
    case "config_key": {
      const a = f.fix.find((x) => x.action === "rename_configmap_key");
      return a ? `A setting's name has a typo: "${a.old}" instead of "${a.new}".` : "A setting's name has a typo.";
    }
    case "service_selector":
      return "Traffic is sent to a label no app has, so nobody receives it.";
    case "template_regression":
      if (f.category === "scheduling" && f.evidence.some((e) => e.includes("Insufficient cpu")))
        return "It asks for more processing power than any server has, so it can't start.";
      return (
        {
          image: "The latest update points to an app version that doesn't exist (a typo).",
          resources: "It needs more memory than it's allowed to use, so it keeps getting stopped.",
          probe: "Its health check is set up wrong, so it looks broken even when it isn't.",
          scheduling: "It asks for a server that doesn't exist, so it can't start anywhere.",
        } as Record<string, string>
      )[f.category] ?? "The latest update broke it; the version before it worked.";
    default:
      return f.summary;
  }
}

export function action(a: Action): string {
  switch (a.action) {
    case "scale_deployment":
      return `Bring back ${a.replicas} copies`;
    case "rollback_deployment":
      return "Go back to the last version that worked";
    case "restart_deployment":
      return "Restart it so it reads the corrected setting";
    case "patch_service":
      return a.target_port ? "Send traffic to the right port" : "Send traffic back to the right app";
    case "rename_configmap_key":
      return `Rename the setting to "${a.new}"`;
  }
}

export function reason(text: string, all: string): string {
  if (all.includes("does not exist") || all.includes("cannot be recovered"))
    return "A deleted password can't be guessed. A person has to restore it, so Nabd changed nothing.";
  if (text.startsWith("no diagnosis")) return "Nabd didn't recognise this problem, so it changed nothing and called a person.";
  if (text.startsWith("the fix was applied")) return "Its fix didn't help, so it undid it and called a person.";
  if (text.startsWith("a human did not approve")) return "You declined the change, so nothing was changed.";
  if (text.startsWith("the policy gate")) return "The fix wasn't on the approved list, so Nabd refused to do it.";
  return text;
}
