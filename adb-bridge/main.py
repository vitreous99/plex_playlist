"""
ADB Bridge — FastAPI service for Android Device Bridge (ADB) orchestration.

Exposes HTTP endpoints to wake Nvidia Shield and launch applications
via ADB over TCP. All ADB commands are executed asynchronously with timeouts.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

# ============================================================================
# Configuration
# ============================================================================
SHIELD_IP = os.getenv("SHIELD_IP", "192.168.1.100")
PLEXAMP_PACKAGE = os.getenv("PLEXAMP_PACKAGE", "com.plexapp.plexamp")
PLEXAMP_ACTIVITY = os.getenv("PLEXAMP_ACTIVITY", ".MainActivity")
WAKE_DELAY_SECONDS = int(os.getenv("WAKE_DELAY_SECONDS", "8"))
ADB_TIMEOUT = 10.0  # seconds

# ============================================================================
# Logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("adb_bridge")

# ============================================================================
# FastAPI Application
# ============================================================================
app = FastAPI(
    title="ADB Bridge",
    description="Android Device Bridge (ADB) orchestration service",
    version="0.1.0",
)

# ============================================================================
# Models
# ============================================================================
class WakeResponse(BaseModel):
    status: str  # "connected", "awake", "error"
    message: str
    timestamp: datetime
    adb_output: Optional[str] = None

# ============================================================================
# ADB Helper Functions
# ============================================================================
async def run_shell_command(cmd: list, timeout: float = 10.0) -> tuple[bool, str]:
    """
    Execute an arbitrary shell command asynchronously.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        output = (stdout + stderr).decode("utf-8", errors="replace").strip()
        return process.returncode == 0, output
    except asyncio.TimeoutError:
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def run_adb_command(args: list, timeout: float = ADB_TIMEOUT) -> tuple[bool, str]:
    """
    Execute an ADB command asynchronously.

    Args:
        args: List of command arguments (e.g., ["connect", "192.168.1.100:5555"])
        timeout: Command timeout in seconds.

    Returns:
        (success: bool, output: str) — True if command succeeded, False otherwise.
        output contains stdout/stderr joined together.
    """
    cmd_str = f"adb {' '.join(args)}"
    logger.info(f"Running: {cmd_str} (timeout={timeout}s)")
    try:
        process = await asyncio.create_subprocess_exec(
            "adb",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()
        output = f"{stdout_str}\n{stderr_str}".strip()

        success = process.returncode == 0
        logger.info(
            f"ADB {'OK' if success else 'FAIL'} (rc={process.returncode}): {cmd_str}\n"
            f"  stdout: {stdout_str or '(empty)'}\n"
            f"  stderr: {stderr_str or '(empty)'}"
        )

        return success, output

    except asyncio.TimeoutError:
        logger.error(f"ADB TIMEOUT ({timeout}s): {cmd_str}")
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        logger.error(f"ADB EXCEPTION: {cmd_str} -> {e}")
        return False, f"Error: {str(e)}"


# ============================================================================
# API Endpoints
# ============================================================================
@app.get("/health")
async def health():
    """Health check endpoint."""
    success, output = await run_adb_command(["version"], timeout=5.0)
    return {
        "status": "ok" if success else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": output if success else "ADB unavailable",
    }


@app.post("/connect")
async def connect(ip: Optional[str] = None) -> WakeResponse:
    """
    Establish ADB connection to Shield.

    Args:
        ip: Shield IP:port (default from SHIELD_IP env var).

    Returns:
        WakeResponse with connection status.
    """
    target_ip = ip or f"{SHIELD_IP}:5555"
    logger.info(f"Attempting ADB connection to {target_ip}")

    success, output = await run_adb_command(["connect", target_ip])

    return WakeResponse(
        status="connected" if success else "error",
        message=output if output else ("Connected successfully" if success else "Connection failed"),
        timestamp=datetime.now(timezone.utc),
        adb_output=output,
    )


@app.post("/wake")
async def wake(ip: Optional[str] = None) -> WakeResponse:
    """
    Full wake sequence: connect → wake screen → launch Plexamp → wait for registration.

    Args:
        ip: Shield IP:port (default from SHIELD_IP env var).

    Returns:
        WakeResponse with wake status and timestamps.
    """
    target_ip = ip or f"{SHIELD_IP}:5555"
    target_device = f"{target_ip.split(':')[0]}" if ":" in target_ip else target_ip
    adb_device_spec = target_ip  # Use full IP:port for ADB commands

    logger.info(f"Starting wake sequence for {adb_device_spec}")

    # Step 1: Ensure ADB connection
    logger.info(f"Step 1/4: Connecting to {adb_device_spec}")
    connect_success, connect_output = await run_adb_command(["connect", adb_device_spec])
    if not connect_success:
        return WakeResponse(
            status="error",
            message=f"Failed to connect: {connect_output}",
            timestamp=datetime.now(timezone.utc),
            adb_output=connect_output,
        )

    # Step 2: Wake the device (send key event)
    logger.info(f"Step 2/4: Sending KEYCODE_WAKEUP to {adb_device_spec}")
    wake_success, wake_output = await run_adb_command(
        ["-s", adb_device_spec, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
        timeout=ADB_TIMEOUT,
    )
    if not wake_success:
        logger.warning(f"Wake key event may have failed: {wake_output}")
        # Don't return error; continue anyway

    # Step 3: Launch Plexamp
    plexamp_component = f"{PLEXAMP_PACKAGE}/{PLEXAMP_ACTIVITY}"
    logger.info(f"Step 3/4: Launching {plexamp_component}")
    launch_success, launch_output = await run_adb_command(
        ["-s", adb_device_spec, "shell", "am", "start", "-n", plexamp_component],
        timeout=ADB_TIMEOUT,
    )
    if not launch_success:
        return WakeResponse(
            status="error",
            message=f"Failed to launch Plexamp: {launch_output}",
            timestamp=datetime.now(timezone.utc),
            adb_output=launch_output,
        )

    # Step 4: Wait for Plexamp to register with Plex Server
    logger.info(f"Step 4/4: Waiting {WAKE_DELAY_SECONDS}s for Plexamp to boot and register")
    await asyncio.sleep(WAKE_DELAY_SECONDS)

    return WakeResponse(
        status="awake",
        message=f"Shield woken successfully. Plexamp launched and waiting {WAKE_DELAY_SECONDS}s for registration.",
        timestamp=datetime.now(timezone.utc),
        adb_output=launch_output,
    )


@app.post("/disconnect")
async def disconnect(ip: Optional[str] = None) -> WakeResponse:
    """
    Disconnect ADB from Shield.

    Args:
        ip: Shield IP:port (default from SHIELD_IP env var).

    Returns:
        WakeResponse with disconnection status.
    """
    target_ip = ip or f"{SHIELD_IP}:5555"
    logger.info(f"Disconnecting from {target_ip}")

    success, output = await run_adb_command(["disconnect", target_ip])

    return WakeResponse(
        status="ok" if success else "error",
        message=output if output else ("Disconnected successfully" if success else "Disconnection failed"),
        timestamp=datetime.now(timezone.utc),
        adb_output=output,
    )


@app.get("/debug/network")
async def debug_network(ip: Optional[str] = None):
    """
    Network diagnostics: ping, route check, ADB device list, and
    port reachability for the Shield.
    """
    target_host = ip or SHIELD_IP
    target_adb = f"{target_host}:5555"
    results = {}

    # Container's own IP / routes
    ok, out = await run_shell_command(["ip", "addr", "show"], timeout=5)
    results["container_interfaces"] = out

    ok, out = await run_shell_command(["ip", "route"], timeout=5)
    results["container_routes"] = out

    # Ping the Shield (3 packets, 2s deadline)
    ok, out = await run_shell_command(
        ["ping", "-c", "3", "-W", "2", target_host], timeout=10
    )
    results["ping"] = {"success": ok, "output": out}

    # ADB version
    ok, out = await run_adb_command(["version"], timeout=5)
    results["adb_version"] = out

    # ADB devices
    ok, out = await run_adb_command(["devices", "-l"], timeout=5)
    results["adb_devices"] = out

    # Quick ADB connect attempt with short timeout
    ok, out = await run_adb_command(["connect", target_adb], timeout=15)
    results["adb_connect"] = {"success": ok, "output": out}

    # Environment
    results["config"] = {
        "SHIELD_IP": SHIELD_IP,
        "target": target_adb,
        "ADB_TIMEOUT": ADB_TIMEOUT,
    }

    return results
