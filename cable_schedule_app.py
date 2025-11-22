import yaml
import streamlit as st
from pathlib import Path

# ---- Helpers ----------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {
            "version": 1,
            "patch_panels": [],
            "outlets": [],
            "devices": [],
            "cables": [],
            "patch_leads": [],
        }
    with path.open() as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict):
    with path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def select_id(options, label, key):
    if not options:
        st.warning(f"No {label} defined yet")
        return None
    return st.selectbox(label, options, key=key)


# ---- Streamlit App ----------------------------------------------------------

st.set_page_config(page_title="Cable Schedule Editor", layout="wide")
st.title("📋 Cable Schedule Editor (YAML)")

yaml_path_str = st.text_input(
    "Path to cable schedule YAML file",
    value="cable_schedule.yaml",
    help="Local path on the machine running Streamlit.",
)
yaml_path = Path(yaml_path_str)

if "data" not in st.session_state:
    st.session_state.data = load_yaml(yaml_path)

data = st.session_state.data

col1, col2 = st.columns(2)

with col1:
    st.subheader("Patch Panels")
    st.dataframe(data.get("patch_panels", []))

    st.subheader("Outlets")
    st.dataframe(data.get("outlets", []))

    st.subheader("Devices")
    st.dataframe(data.get("devices", []))

with col2:
    st.subheader("Cables (Outlet → Patch Panel)")
    st.dataframe(data.get("cables", []))

    st.subheader("Patch Leads (Patch Panel → Device Port)")
    st.dataframe(data.get("patch_leads", []))

st.markdown("---")

# ---- Add Cable Form ---------------------------------------------------------

st.header("➕ Add Horizontal Cable (Outlet → Patch Panel)")
with st.form("add_cable_form"):
    outlets = [o["id"] for o in data.get("outlets", [])]
    panels = [p["id"] for p in data.get("patch_panels", [])]

    outlet_id = select_id(outlets, "Outlet", key="cable_outlet")
    panel_id = select_id(panels, "Patch Panel", key="cable_panel")

    pp_port = st.number_input("Patch Panel Port", min_value=1, step=1, value=1)
    cable_type = st.text_input("Cable Type", value="cat6")
    cable_colour = st.text_input("Cable Colour", value="blue")
    length_m = st.number_input("Cable Length (m)", min_value=0.0, value=10.0, step=0.5)

    submitted_cable = st.form_submit_button("Add Cable")

    if submitted_cable and outlet_id and panel_id:
        new_id = f"CABLE-{len(data.get('cables', [])) + 1:03d}"
        cable = {
            "id": new_id,
            "type": cable_type,
            "colour": cable_colour,
            "length_m": length_m,
            "from": {"type": "outlet", "id": outlet_id},
            "to": {"type": "patch_panel", "panel_id": panel_id, "port": int(pp_port)},
        }
        data.setdefault("cables", []).append(cable)
        st.success(f"Added cable {new_id}")
        st.session_state.data = data

# ---- Add Patch Lead Form ----------------------------------------------------

st.header("➕ Add Patch Lead (Patch Panel → Device Port)")
with st.form("add_lead_form"):
    panels = [p["id"] for p in data.get("patch_panels", [])]
    devices = [d["id"] for d in data.get("devices", [])]

    panel_id = select_id(panels, "Patch Panel", key="lead_panel")
    pp_port = st.number_input("Patch Panel Port", min_value=1, step=1, value=1, key="lead_port")

    device_id = select_id(devices, "Device", key="lead_device")

    device_ports = []
    if device_id:
        dev = next((d for d in data.get("devices", []) if d["id"] == device_id), None)
        if dev:
            device_ports = [p["name"] for p in dev.get("ports", [])]

    device_port = st.selectbox("Device Port", device_ports, key="lead_device_port")

    lead_type = st.text_input("Patch Lead Type", value="cat6")
    lead_colour = st.text_input("Patch Lead Colour", value="yellow")
    lead_length = st.number_input("Lead Length (m)", min_value=0.0, value=1.0, step=0.5)

    submitted_lead = st.form_submit_button("Add Patch Lead")

    if submitted_lead and panel_id and device_id and device_port:
        new_id = f"LEAD-{len(data.get('patch_leads', [])) + 1:03d}"
        lead = {
            "id": new_id,
            "type": lead_type,
            "colour": lead_colour,
            "length_m": lead_length,
            "from": {"type": "patch_panel", "panel_id": panel_id, "port": int(pp_port)},
            "to": {"type": "device_port", "device_id": device_id, "port": device_port},
        }
        data.setdefault("patch_leads", []).append(lead)
        st.success(f"Added patch lead {new_id}")
        st.session_state.data = data

st.markdown("---")

if st.button("💾 Save YAML"):
    save_yaml(yaml_path, data)
    st.success(f"Saved to {yaml_path}")