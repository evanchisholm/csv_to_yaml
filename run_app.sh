#!/bin/bash
# Run the Streamlit app using uv

cd "$(dirname "$0")"
uv run streamlit run cable_schedule_app.py

