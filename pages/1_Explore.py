import json

import streamlit as st
from dotenv import load_dotenv

import store.db as db

load_dotenv()
db.init()

st.set_page_config(page_title="Canon — Explore", page_icon="📚", layout="wide")
st.title("Explore")
st.caption("Browse all stored topics, designs, and sessions.")

tab_topics, tab_designs, tab_sessions = st.tabs(["Topics", "Designs", "Sessions"])

with tab_topics:
    topics = db.list_topics()
    if not topics:
        st.info("No topics stored yet. Run a discovery on the Deploy page.")
    else:
        st.markdown(f"**{len(topics)} topic(s)**")
        for t in topics:
            label = f"#{t['id']} — {t['topic']}"
            with st.expander(label):
                col1, col2 = st.columns(2)
                col1.markdown(f"**Format:** {t.get('format_suggestion') or '—'}")
                col1.markdown(f"**Batch:** `{t.get('batch_run_id') or '—'}`")
                col1.markdown(f"**Created:** {str(t.get('created_at', ''))[:16]}")
                col2.markdown(f"**Query:** {t.get('query') or '_(full scan)_'}")
                context = t.get("context_text") or ""
                if context:
                    st.markdown("---")
                    st.markdown("**KG Context**")
                    st.markdown(context[:3000] + ("…" if len(context) > 3000 else ""))

with tab_designs:
    designs = db.list_designs()
    if not designs:
        st.info("No designs stored yet. Run a design on the Deploy page.")
    else:
        st.markdown(f"**{len(designs)} design(s)**")
        for d in designs:
            try:
                p = json.loads(d.get("params_json") or "{}")
            except Exception:
                p = {}
            label = f"#{d['id']} — {p.get('topic') or 'Design ' + str(d['id'])}"
            if d.get("selected"):
                label += "  ✓"
            with st.expander(label):
                st.markdown(f"**Goal:** {p.get('goal') or '—'}")
                st.markdown(
                    f"**Topic ID:** {d.get('topic_id')}  "
                    f"·  **Template:** `{d.get('template_id') or '—'}`  "
                    f"·  **Created:** {str(d.get('created_at', ''))[:16]}"
                )
                st.code(json.dumps(p, indent=2), language="json")

with tab_sessions:
    sessions = db.list_sessions()
    if not sessions:
        st.info("No sessions created yet. Complete a deploy run first.")
    else:
        st.markdown(f"**{len(sessions)} session(s)**")
        for s in sessions:
            hid = s.get("harmonica_session_id") or "unknown"
            with st.expander(f"#{s['id']} — {hid}"):
                st.markdown(f"**Status:** {s.get('status') or '—'}")
                st.markdown(f"**Design ID:** {s.get('design_id') or '—'}")
                st.markdown(f"**Created:** {str(s.get('created_at', ''))[:16]}")
                url = s.get("join_url") or ""
                if url:
                    st.markdown(f"**Participant URL:** [{url}]({url})")
