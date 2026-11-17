"""Run the self-hosted dashboard and marketing site for local development.

Both servers bind to loopback and are stopped together. Restart after code changes.
Feedback mail is disabled so a copied production key cannot send from a preview.
"""

import argparse
import logging
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
START_TIMEOUT = 15
STOP_TIMEOUT = 5


def configure():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)

    def port(name, default):
        try:
            value = int(os.environ.get(name, default))
            if 1 <= value <= 65535:
                return value
        except ValueError:
            pass
        raise RuntimeError(f"{name} must be an integer between 1 and 65535.")

    if "CONDUCTOR_PORT" in os.environ:
        dashboard = port("CONDUCTOR_PORT", 5000)
        website = dashboard + 1
    else:
        dashboard = port("DINKYDASH_PORT", 5000)
        website = port("DINKYDASH_WEBSITE_PORT", dashboard + 1)
    if website > 65535 or website == dashboard:
        raise RuntimeError("Dashboard and website need distinct ports between 1 and 65535.")

    os.environ["SENDGRID_API_KEY"] = ""
    return {"Dashboard": dashboard, "Website": website}


def serve(name, port, ready):
    """Signal readiness only after the real app has initialized and bound its port."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logging.basicConfig(level=logging.INFO, format=f"[{name}] %(message)s")
    try:
        from werkzeug.serving import make_server

        if name == "Dashboard":
            from web import create_app
            app = create_app()
        else:
            from website.site import create_site_app
            app = create_site_app()
        with make_server(HOST, port, app, threaded=True) as server:
            ready.send(True)
            ready.close()
            server.serve_forever()
    except (Exception, SystemExit) as exc:
        print(f"{name} failed to start or serve on port {port} ({type(exc).__name__}): {exc}",
              file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    finally:
        ready.close()


def supervise(ports):
    context = multiprocessing.get_context("spawn")
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for name, port in ports.items():
            if stopping:
                return 0
            reader, writer = context.Pipe(duplex=False)
            process = context.Process(target=serve, args=(name, port, writer), name=name)
            process.start()
            writer.close()
            children.append((name, process, reader))
            print(f"Starting {name} (PID {process.pid}) on port {port}.", flush=True)

        pending = {name for name, _, _ in children}
        deadline = time.monotonic() + START_TIMEOUT
        while not stopping:
            for name, process, reader in children:
                if process.exitcode is not None:
                    raise RuntimeError(f"{name} exited unexpectedly (status {process.exitcode}); stopping both apps.")
                if name in pending and reader.poll():
                    try:
                        reader.recv()
                    except EOFError:
                        raise RuntimeError(f"{name} failed during startup; stopping both apps.") from None
                    pending.remove(name)
                    if not pending:
                        print(f"Dashboard: http://{HOST}:{ports['Dashboard']}/", flush=True)
                        print(f"Website:   http://{HOST}:{ports['Website']}/", flush=True)
                        print("Restart this command after code/content changes. "
                              "Ctrl-C stops both apps.", flush=True)
            if pending and time.monotonic() >= deadline:
                raise RuntimeError(f"Startup timed out: {', '.join(sorted(pending))}; stopping both apps.")
            time.sleep(0.1)
        return 0
    finally:
        for _, process, reader in children:
            reader.close()
            if process.is_alive():
                process.terminate()
        deadline = time.monotonic() + STOP_TIMEOUT
        for _, process, _ in children:
            process.join(max(0, deadline - time.monotonic()))
            if process.is_alive():
                process.kill()
                process.join()
        for sig, handler in previous.items():
            signal.signal(sig, handler)



def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    try:
        return supervise(configure())
    except ImportError as exc:
        print(f"Development dependency missing ({exc.name}); install requirements-dev.txt.", file=sys.stderr)
    except (RuntimeError, OSError) as exc:
        print(f"Development startup failed: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
