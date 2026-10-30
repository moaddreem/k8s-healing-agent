"""Everything Nabd knows about the cluster goes through this file (kubectl in, JSON out)."""
import json
import subprocess


class KubeError(RuntimeError):
    pass


def kubectl(*args, input_text=None, timeout=60):
    """Run kubectl and return (returncode, stdout, stderr)."""
    p = subprocess.run(
        ["kubectl", *args], input=input_text, capture_output=True, text=True, timeout=timeout
    )
    return p.returncode, p.stdout, p.stderr


def get_json(ns, kind, name=None):
    args = ["get", kind] + ([name] if name else []) + ["-n", ns, "-o", "json"]
    rc, out, err = kubectl(*args)
    if rc != 0:
        raise KubeError(f"kubectl {' '.join(args)}: {err.strip()}")
    return json.loads(out)


def pod_logs(ns, pod, container, previous=False, tail=15):
    args = ["logs", pod, "-n", ns, "-c", container, f"--tail={tail}"]
    if previous:
        args.append("--previous")
    rc, out, _ = kubectl(*args)
    return out.strip() if rc == 0 else ""
