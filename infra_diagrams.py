import yaml
import sys
import subprocess
from pathlib import Path
import re

# ============ Helpers ============

def safe_alias(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def q(s: str) -> str:
    return s.replace('"', '\\"')


def overcommit(allocated: float, capacity: float):
    if capacity <= 0:
        return allocated, "-"
    return allocated, f"{(allocated / capacity) * 100:.1f}%"


def render_file(puml_file: Path, formats=("png", "svg")):
    for fmt in formats:
        try:
            print(f"[INFO] Rendering {fmt.upper()} for {puml_file.name}")
            subprocess.run(["plantuml", f"-t{fmt}", str(puml_file)], check=True)
        except FileNotFoundError:
            print("[WARN] 'plantuml' not found on PATH – skipping rendering.")
            break
        except subprocess.CalledProcessError as e:
            print(f"[WARN] PlantUML failed for {puml_file}: {e}")


# ============ Topology (Networks + Compute + Storage + Apps + Security) ============

def generate_topology_puml(site: dict) -> str:
    nets = site.get("networks", [])
    hv_list = site.get("hypervisors", [])
    storage_pools = site.get("storage_pools", [])
    applications = site.get("applications", [])
    security_devices = site.get("security_devices", [])
    databases = site.get("databases", [])

    # Application domain colors
    domain_colors = {}
    default_app_colors = ["#CCE5FF", "#FFDDBB", "#E0E0E0", "#D4EDDA", "#F7D7E0"]
    dc_index = 0
    for app in applications:
        domain = app.get("domain", "general")
        if domain not in domain_colors:
            domain_colors[domain] = default_app_colors[dc_index % len(default_app_colors)]
            dc_index += 1

    lines = []
    lines.append("@startuml")
    lines.append(f"title Topology – {site['name']}")
    lines.append("skinparam shadowing false")
    lines.append("skinparam defaultTextAlignment left")
    lines.append("skinparam packageStyle rectangle")

    # -------- LEGEND --------
    lines.append("legend left")
    lines.append("== Hypervisor Colors ==")
    for hv in hv_list:
        if "color" in hv:
            lines.append(f"|<back:{hv['color']}> {hv['name']} </back>| {hv['color']} |")

    if nets:
        lines.append("== Network Roles ==")
        seen_roles = set()
        for n in nets:
            r = n.get("role")
            if r and r not in seen_roles:
                seen_roles.add(r)
                lines.append(f"| {r} | VLAN {n.get('vlan','')} | {n.get('cidr','')} |")

    if storage_pools:
        lines.append("== Storage Pools ==")
        for sp in storage_pools:
            lines.append(f"| {sp['name']} | {sp['type']} | {sp.get('size_gb','')} GB |")

    if security_devices:
        lines.append("== Security Devices ==")
        for sd in security_devices:
            lines.append(f"| {sd['name']} | {sd['type']} | {sd.get('role','')} |")

    if applications:
        lines.append("== Application Domains ==")
        for domain, color in domain_colors.items():
            lines.append(f"|<back:{color}> {domain} </back>| app domain |")

    if databases:
        lines.append("== Databases ==")
        for db in databases:
            lines.append(f"| {db['name']} | {db['engine']} {db.get('version','')} |")

    lines.append("endlegend")
    lines.append("")

    # -------- NETWORK LAYER --------
    lines.append("package \"Network Layer\" {")
    net_alias = {}
    for n in nets:
        alias = safe_alias("net_" + n["name"])
        net_alias[n["name"]] = alias
        label_parts = [n["name"]]
        if n.get("cidr"):
            label_parts.append(n["cidr"])
        if n.get("vlan"):
            label_parts.append(f"VLAN {n['vlan']}")
        if n.get("role"):
            label_parts.append(n["role"])
        # Use single line with separators for cloud labels (multiline not well supported)
        label = " - ".join(label_parts)
        lines.append(f'  cloud "{q(label)}" as {alias}')
    # represent 'internet' if any security devices reference it
    if any("internet" in (sd.get("front_network", ""), *sd.get("inline_between", [])) for sd in security_devices):
        lines.append('  cloud "Internet" as net_internet')
        net_alias["internet"] = "net_internet"
    lines.append("}")
    lines.append("")

    # -------- SECURITY LAYER --------
    if security_devices:
        lines.append("package \"Security Layer\" {")
        sec_alias = {}
        for sd in security_devices:
            alias = safe_alias("sec_" + sd["name"])
            sec_alias[sd["name"]] = alias
            label = "\\n".join([
                sd["name"],
                f"type: {sd['type']}",
                f"role: {sd.get('role','')}"
            ])
            lines.append(f'  rectangle "{q(label)}" as {alias} #FFEECC')
        lines.append("}")
        lines.append("")
    else:
        sec_alias = {}

    # -------- COMPUTE LAYER --------
    hv_alias = {}
    vm_alias = {}

    lines.append("package \"Compute Layer\" {")
    for hv in hv_list:
        name = hv["name"]
        alias = safe_alias("hv_" + name)
        hv_alias[name] = alias
        color = hv.get("color", "")

        hv_cpu = float(hv.get("cpu", 0))
        hv_ram = float(hv.get("ram_gb", 0))
        hv_storage = float(hv.get("storage_gb", 0))
        vm_cpu_total = sum(float(v.get("cpu", 0)) for v in hv.get("vms", []))
        vm_ram_total = sum(float(v.get("ram_gb", 0)) for v in hv.get("vms", []))
        vm_storage_total = sum(float(v.get("storage_gb", 0)) for v in hv.get("vms", []))

        _, cpu_oc = overcommit(vm_cpu_total, hv_cpu)
        _, ram_oc = overcommit(vm_ram_total, hv_ram)
        _, st_oc = overcommit(vm_storage_total, hv_storage)

        hv_header = "\\n".join([
            name,
            f"CPU: {hv_cpu} (VMs: {vm_cpu_total}, {cpu_oc})",
            f"RAM: {hv_ram} GB (VMs: {vm_ram_total} GB, {ram_oc})",
            f"Storage: {hv_storage} GB (VMs: {vm_storage_total} GB, {st_oc})",
        ])

        color_suffix = f" {color}" if color else ""
        lines.append(f'  package "{q(hv_header)}" as {alias}{color_suffix} {{')

        for vm in hv.get("vms", []):
            vname = vm["name"]
            valias = safe_alias("vm_" + vname)
            vm_alias[vname] = valias
            label = "\\n".join([
                vname,
                f"OS: {vm.get('os','')}",
                f"CPU: {vm.get('cpu','')}",
                f"RAM: {vm.get('ram_gb','')} GB",
                f"Disk: {vm.get('storage_gb','')} GB",
            ])
            lines.append(f'    node "{q(label)}" as {valias}')
        lines.append("  }")
    lines.append("}")
    lines.append("")

    # -------- STORAGE LAYER --------
    sp_alias = {}
    lines.append("package \"Storage Layer\" {")
    for sp in storage_pools:
        alias = safe_alias("sp_" + sp["name"])
        sp_alias[sp["name"]] = alias
        label = "\\n".join([
            sp["name"],
            f"type: {sp['type']}",
            f"size: {sp.get('size_gb','')} GB"
        ])
        lines.append(f'  database "{q(label)}" as {alias}')
    lines.append("}")
    lines.append("")

    # -------- APPLICATION LAYER --------
    app_alias = {}
    lines.append("package \"Application Layer\" {")
    for app in applications:
        name = app["name"]
        alias = safe_alias("app_" + name)
        app_alias[name] = alias
        domain = app.get("domain", "general")
        color = domain_colors.get(domain, "#E0E0E0")

        role = app.get("role", "")
        desc = app.get("description", "")
        ports = app.get("exposed_ports", [])
        tier = app.get("tier", "")
        stack = ", ".join(app.get("tech_stack", []))

        label_lines = [name]
        if role:
            label_lines.append(f"role: {role}")
        if tier:
            label_lines.append(f"tier: {tier}")
        if desc:
            label_lines.append(desc)
        if ports:
            label_lines.append("ports: " + ", ".join(str(p) for p in ports))
        if stack:
            label_lines.append("tech: " + stack)

        label = "\\n".join(label_lines)
        lines.append(f'  component "{q(label)}" as {alias} {color}')
    lines.append("}")
    lines.append("")

    # -------- Relationships --------

    # VM -> Networks
    for hv in hv_list:
        for vm in hv.get("vms", []):
            valias = vm_alias[vm["name"]]
            for nic in vm.get("networks", []):
                nname = nic["name"]
                nalias = net_alias.get(nname)
                if nalias:
                    ip = nic.get("ip", "")
                    line = f"{valias} --> {nalias}"
                    if ip:
                        line += f' : "{ip}"'
                    lines.append(line)

    # VM -> Storage
    for hv in hv_list:
        for vm in hv.get("vms", []):
            sp = vm.get("storage_pool")
            if sp and sp in sp_alias:
                lines.append(f"{vm_alias[vm['name']]} ..> {sp_alias[sp]} : storage")

    # Hypervisor -> Storage pool
    for sp in storage_pools:
        for hv in sp.get("hypervisors", []):
            if hv in hv_alias:
                lines.append(f"{hv_alias[hv]} ..> {sp_alias[sp['name']]} : uses")

    # Application -> VM
    for app in applications:
        hosted_on = app.get("hosted_on")
        if hosted_on and hosted_on in vm_alias:
            lines.append(f"{app_alias[app['name']]} --> {vm_alias[hosted_on]} : hosted on")

    # Application -> Application
    for app in applications:
        for dep in app.get("depends_on", []):
            if dep in app_alias:
                lines.append(f"{app_alias[app['name']]} ..> {app_alias[dep]} : depends on")

    # Security devices: connect to networks
    for sd in security_devices:
        salias = safe_alias("sec_" + sd["name"])
        front = sd.get("front_network")
        back = sd.get("back_network")
        inline = sd.get("inline_between", [])
        if front and front in net_alias:
            lines.append(f"{net_alias[front]} --> {salias}")
        if back and back in net_alias:
            lines.append(f"{salias} --> {net_alias[back]}")
        if inline and len(inline) == 2:
            left, right = inline
            if left in net_alias and right in net_alias:
                # Split chained relationship into two separate lines (PlantUML doesn't support chained syntax)
                lines.append(f"{net_alias[left]} --> {salias}")
                lines.append(f"{salias} --> {net_alias[right]}")

    lines.append("@enduml")
    return "\n".join(lines)


# ============ Microservice / Application Dependency Diagram ============

def generate_microservices_puml(site: dict) -> str:
    apps = site.get("applications", [])
    if not apps:
        return "@startuml\n' No applications defined\n@enduml\n"

    # domain colors as before
    domain_colors = {}
    default_app_colors = ["#CCE5FF", "#FFDDBB", "#E0E0E0", "#D4EDDA", "#F7D7E0"]
    dc_index = 0
    for app in apps:
        domain = app.get("domain", "general")
        if domain not in domain_colors:
            domain_colors[domain] = default_app_colors[dc_index % len(default_app_colors)]
            dc_index += 1

    lines = []
    lines.append("@startuml")
    lines.append(f"title Microservice / Application Dependencies – {site['name']}")
    lines.append("skinparam componentStyle rectangle")
    lines.append("skinparam shadowing false")

    lines.append("legend left")
    lines.append("== Domains ==")
    for d, c in domain_colors.items():
        lines.append(f"|<back:{c}> {d} </back>| domain |")
    lines.append("endlegend")
    lines.append("")

    app_alias = {}
    # Group by domain
    domains = {}
    for app in apps:
        domains.setdefault(app.get("domain", "general"), []).append(app)

    for domain, app_list in domains.items():
        color = domain_colors[domain]
        lines.append(f'package "{q(domain)}" {color} {{')
        for app in app_list:
            name = app["name"]
            alias = safe_alias("app_" + name)
            app_alias[name] = alias
            tier = app.get("tier", "")
            role = app.get("role", "")
            label = "\\n".join(filter(None, [name, f"tier: {tier}", f"role: {role}"]))
            lines.append(f'  component "{q(label)}" as {alias}')
        lines.append("}")
        lines.append("")

    # Dependencies
    for app in apps:
        for dep in app.get("depends_on", []):
            if dep in app_alias:
                lines.append(f"{app_alias[app['name']]} --> {app_alias[dep]}")

    lines.append("@enduml")
    return "\n".join(lines)


# ============ Database Schema Diagram (simplified ER) ============

def generate_databases_puml(site: dict) -> str:
    dbs = site.get("databases", [])
    if not dbs:
        return "@startuml\n' No databases defined\n@enduml\n"

    lines = []
    lines.append("@startuml")
    lines.append(f"title Database Schemas – {site['name']}")
    lines.append("skinparam classAttributeIconSize 0")
    lines.append("skinparam shadowing false")

    db_alias = {}
    table_alias = {}

    for db in dbs:
        dname = db["name"]
        dalias = safe_alias("db_" + dname)
        db_alias[dname] = dalias
        label = f"{dname}\\n{db['engine']} {db.get('version','')}"
        lines.append(f'package "{q(label)}" as {dalias} {{')
        for table in db.get("schema", {}).get("tables", []):
            tname = table["name"]
            talias = safe_alias(f"{dname}_{tname}")
            table_alias[(dname, tname)] = talias
            lines.append(f"  class {talias} {{")
            for col in table.get("columns", []):
                marker = ""
                if col.get("pk"):
                    marker = " <<PK>>"
                elif col.get("fk"):
                    marker = " <<FK>>"
                lines.append(f"    {col['name']} : {col['type']}{marker}")
            lines.append("  }")
        lines.append("}")
        lines.append("")

    # basic FK relationships if present
    for db in dbs:
        dname = db["name"]
        for table in db.get("schema", {}).get("tables", []):
            tname = table["name"]
            talias = table_alias.get((dname, tname))
            for col in table.get("columns", []):
                fk = col.get("fk")
                if fk:
                    # fk format: "ref_db.ref_table.ref_column" or "ref_table.ref_column"
                    parts = fk.split(".")
                    if len(parts) == 3:
                        ref_db, ref_table, _ = parts
                    elif len(parts) == 2:
                        ref_db = dname
                        ref_table, _ = parts
                    else:
                        continue
                    ref_alias = table_alias.get((ref_db, ref_table))
                    if ref_alias:
                        lines.append(f"{talias} --> {ref_alias} : {col['name']}")

    lines.append("@enduml")
    return "\n".join(lines)


# ============ Flow / Sequence Diagrams ============

def generate_flow_puml(site: dict, flow: dict) -> str:
    lines = []
    lines.append("@startuml")
    lines.append(f'title Flow – {q(flow.get("name",""))} ({site["name"]})')
    lines.append("skinparam shadowing false")

    participants = flow.get("participants", [])
    # apps may appear as participants by name
    app_names = {app["name"] for app in site.get("applications", [])}

    for p in participants:
        if p in app_names:
            # mark it as component-like participant
            lines.append(f'participant {safe_alias("app_" + p)} as "{q(p)}"')
        else:
            lines.append(f'actor {safe_alias("actor_" + p)} as "{q(p)}"')

    lines.append("")
    for step in flow.get("steps", []):
        src = step["from"]
        dst = step["to"]
        msg = step.get("message", "")
        if src in app_names:
            src_alias = safe_alias("app_" + src)
        else:
            src_alias = safe_alias("actor_" + src)
        if dst in app_names:
            dst_alias = safe_alias("app_" + dst)
        else:
            dst_alias = safe_alias("actor_" + dst)
        lines.append(f"{src_alias} -> {dst_alias} : {q(msg)}")

    lines.append("@enduml")
    return "\n".join(lines)


# ============ Main driver ============

def main():
    if len(sys.argv) < 3:
        print("Usage: python infra_diagrams.py big_infra.yaml output_dir/")
        sys.exit(1)

    input_yaml = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    data = yaml.safe_load(input_yaml.read_text())

    for site in data.get("sites", []):
        site_name = site["name"]
        print(f"[INFO] Processing site: {site_name}")

        # Topology
        topology_puml = generate_topology_puml(site)
        topology_file = out_dir / f"{site_name}_topology.puml"
        topology_file.write_text(topology_puml, encoding="utf-8")
        render_file(topology_file)

        # Microservices
        micro_puml = generate_microservices_puml(site)
        micro_file = out_dir / f"{site_name}_microservices.puml"
        micro_file.write_text(micro_puml, encoding="utf-8")
        render_file(micro_file)

        # Databases
        db_puml = generate_databases_puml(site)
        db_file = out_dir / f"{site_name}_databases.puml"
        db_file.write_text(db_puml, encoding="utf-8")
        render_file(db_file)

        # Flows
        for flow in site.get("flows", []):
            fname = flow.get("name", "flow")
            flow_puml = generate_flow_puml(site, flow)
            flow_file = out_dir / f"{site_name}_flow_{safe_alias(fname)}.puml"
            flow_file.write_text(flow_puml, encoding="utf-8")
            render_file(flow_file)

    print("[INFO] All diagrams generated.")


if __name__ == "__main__":
    main()