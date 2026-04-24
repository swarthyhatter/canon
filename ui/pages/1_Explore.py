import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
            fmt = t.get("format_suggestion") or "Open Dialogue"
            label = f"#{t['id']} — {t['topic']}"
            with st.expander(label):
                col_meta, col_fmt = st.columns([4, 1])
                col_meta.caption(
                    f"Query: {t.get('query') or '(full scan)'}  ·  "
                    f"Created: {str(t.get('created_at', ''))[:16]}  ·  "
                    f"Batch: {t.get('batch_run_id') or '—'}"
                )
                col_fmt.markdown(f"`{fmt}`")
                context = t.get("context_text") or ""
                if context:
                    st.markdown("---")
                    if len(context) > 1500:
                        st.markdown(context[:1500] + "…")
                        with st.expander("Show full KG context"):
                            st.markdown(context)
                    else:
                        st.markdown(context)

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
            fmt = p.get("format") or d.get("template_id") or "—"
            label = f"#{d['id']} — {p.get('topic') or 'Design ' + str(d['id'])}"
            if d.get("selected"):
                label += "  ✓"
            with st.expander(label):
                st.markdown(f"**{p.get('goal') or '—'}**")
                st.caption(f"Format: `{fmt}`")
                if p.get("critical"):
                    st.markdown(f"*{p['critical']}*")
                st.caption(
                    f"Topic ID: {d.get('topic_id')}  ·  "
                    f"Template: `{d.get('template_id') or '—'}`  ·  "
                    f"Created: {str(d.get('created_at', ''))[:16]}"
                )
                prompt_text = p.get("prompt") or ""
                if prompt_text:
                    st.markdown("**Facilitation Script**")
                    st.code(prompt_text, language="text")
                with st.expander("Raw params"):
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
                st.caption(
                    f"Status: {s.get('status') or '—'}  ·  "
                    f"Design ID: {s.get('design_id') or '—'}  ·  "
                    f"Created: {str(s.get('created_at', ''))[:16]}"
                )
                url = s.get("join_url") or ""
                if url:
                    st.markdown("**Participant URL**")
                    st.code(url)
