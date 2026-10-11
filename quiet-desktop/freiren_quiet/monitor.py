"""psutil supplies interval CPU measurements; no command lines or browsing data are read."""

import psutil


class Monitor:
    def __init__(self):
        psutil.cpu_percent()
        self.known = set()
        self.sample()

    def sample(self):
        total = psutil.cpu_percent()
        cores = psutil.cpu_count() or 1
        processes = []
        current = set()
        for process in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                identity = (process.pid, process.info["create_time"])
                current.add(identity)
                percent = process.cpu_percent() / cores
                if identity in self.known and percent >= 0.1:
                    processes.append(
                        {
                            "pid": process.pid,
                            "name": process.info["name"],
                            "cpu_percent": round(percent, 1),
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self.known = current
        processes.sort(key=lambda process: process["cpu_percent"], reverse=True)
        battery = psutil.sensors_battery()
        return {
            "cpu_percent": total,
            "logical_cpus": cores,
            "top_processes": processes[:6],
            "battery_percent": round(battery.percent) if battery else None,
            "plugged": battery.power_plugged if battery else None,
        }
