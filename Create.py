import streamlit as st
from dotenv import load_dotenv

import store.db as db
from agent import SurveyDesigner, TopicAdvisor
from app_utils import get_clients

load_dotenv()
db.init()

st.set_page_config(page_title="Canon — Deploy", page_icon="🔥", layout="wide")
st.title("Deploy a Session")
st.caption("Discover a topic → generate a design → create a Harmonica session")

bonfire, harmonica = get_clients()

# ── initialise state ──────────────────────────────────────────────────────────
for key in ["selected_topic", "selected_design", "created_session",
            "discover_results", "design_results"]:
    if key not in st.session_state:
        st.session_state[key] = None


def clear_topic():
    st.session_state.selected_topic = None
    st.session_state.selected_design = None
    st.session_state.created_session = None
    st.session_state.design_results = None


def clear_design():
    st.session_state.selected_design = None
    st.session_state.created_session = None


def clear_session():
    st.session_state.created_session = None


# ── STEP 1 — DISCOVER ────────────────────────────────────────────────────────
st.markdown("---")

if st.session_state.selected_topic:
    t = st.session_state.selected_topic
    col1, col2 = st.columns([10, 1])
    col1.success(
        f"**Step 1 — Topic selected:** {t['topic']}  "
        f"·  _{t.get('format_suggestion') or 'Open Dialogue'}_"
    )
    col2.button("✕", key="clear_topic", on_click=clear_topic, help="Change topic")
else:
    st.subheader("Step 1 — Discover Topics")

    with st.form("discover_form"):
        col1, col2 = st.columns([4, 1])
        query = col1.text_input(
            "Query",
            placeholder="e.g. community governance  (blank = full KG scan)",
        )
        n = col2.number_input("Variations", min_value=1, max_value=10, value=3)
        run = st.form_submit_button("Discover Topics", use_container_width=True)

    if run:
        with st.spinner("Querying knowledge graph..."):
            advisor = TopicAdvisor(bonfire)
            st.session_state.discover_results = advisor.discover_batch(
                query=query.strip() or None, n=n
            )

    # results from this run
    if st.session_state.discover_results:
        st.markdown("**Results — select a topic to continue**")
        for t in st.session_state.discover_results:
            c1, c2, c3 = st.columns([6, 2, 1])
            c1.markdown(f"**{t['topic']}**  \n{t.get('rationale', '')[:120]}")
            c2.markdown(f"`{t.get('format_suggestion') or '—'}`")
            if c3.button("Select", key=f"pick_t_{t['id']}"):
                st.session_state.selected_topic = t
                st.session_state.design_results = None
                st.rerun()

    # previously stored topics
    stored_topics = db.list_topics()
    if stored_topics:
        with st.expander(f"Or pick from {len(stored_topics)} stored topic(s)"):
            for t in stored_topics:
                c1, c2, c3 = st.columns([6, 2, 1])
                c1.write(t["topic"])
                c2.write(t.get("format_suggestion") or "—")
                if c3.button("Select", key=f"hist_t_{t['id']}"):
                    st.session_state.selected_topic = t
                    st.session_state.design_results = None
                    st.rerun()


# ── STEP 2 — DESIGN ──────────────────────────────────────────────────────────
if st.session_state.selected_topic:
    st.markdown("---")

    if st.session_state.selected_design:
        import json
        d = st.session_state.selected_design
        col1, col2 = st.columns([10, 1])
        col1.success(
            f"**Step 2 — Design selected:** #{d['id']}  ·  {d.get('topic', '')[:60]}  \n"
            f"_{d.get('goal', '')[:100]}_"
        )
        col2.button("✕", key="clear_design", on_click=clear_design, help="Change design")
    else:
        topic = st.session_state.selected_topic
        st.subheader("Step 2 — Generate Designs")
        st.caption(f"Topic: {topic['topic']}")

        with st.form("design_form"):
            n = st.number_input("Variations", min_value=1, max_value=5, value=3)
            run = st.form_submit_button("Generate Designs", use_container_width=True)

        if run:
            with st.spinner("Designing session — this takes 30–60 seconds..."):
                designer = SurveyDesigner(bonfire, harmonica)
                st.session_state.design_results = designer.build_survey_params_from_topic(
                    topic["id"], n=n
                )

        if st.session_state.design_results:
            import json
            st.markdown("**Results — select a design to continue**")
            for d in st.session_state.design_results:
                c1, c2 = st.columns([9, 1])
                with c1.expander(f"**Design #{d['id']}** — {d.get('topic', '')}"):
                    st.markdown(f"**Goal:** {d.get('goal', '')}")
                    st.markdown(f"**Format:** `{d.get('template_id') or '—'}`")
                    st.code(
                        json.dumps(
                            {k: v for k, v in d.items() if k not in ("id", "batch_run_id")},
                            indent=2
                        ),
                        language="json",
                    )
                if c2.button("Select", key=f"pick_d_{d['id']}"):
                    st.session_state.selected_design = d
                    st.rerun()

        stored_designs = db.list_designs(topic_id=topic["id"])
        if stored_designs:
            import json
            with st.expander(f"Or pick from {len(stored_designs)} stored design(s) for this topic"):
                for d in stored_designs:
                    try:
                        p = json.loads(d.get("params_json") or "{}")
                    except Exception:
                        p = {}
                    c1, c2, c3 = st.columns([5, 4, 1])
                    c1.write(p.get("topic") or f"Design #{d['id']}")
                    c2.write((p.get("goal") or "")[:60])
                    if c3.button("Select", key=f"hist_d_{d['id']}"):
                        st.session_state.selected_design = {**p, "id": d["id"]}
                        st.rerun()


# ── STEP 3 — CREATE ───────────────────────────────────────────────────────────
if st.session_state.selected_design:
    st.markdown("---")

    if st.session_state.created_session:
        s = st.session_state.created_session
        join_url = s.get("join_url") or s.get("url") or s.get("participant_url", "")
        session_id = s.get("id") or s.get("session_id", "")
        col1, col2 = st.columns([10, 1])
        col1.success(f"**Step 3 — Session created:** `{session_id}`")
        col2.button("✕", key="clear_session", on_click=clear_session, help="Create another")
    else:
        design = st.session_state.selected_design
        st.subheader("Step 3 — Create Session")
        st.caption(f"Design #{design['id']}: {design.get('topic', '')}")

        with st.form("create_form"):
            template_override = st.text_input(
                "Template ID (optional override)",
                placeholder="leave blank to use design default",
            )
            run = st.form_submit_button("Create Harmonica Session", use_container_width=True)

        if run:
            with st.spinner("Creating session..."):
                designer = SurveyDesigner(bonfire, harmonica)
                session = designer.create_session_from_design(
                    design["id"],
                    template_id=template_override.strip() or None,
                )
            st.session_state.created_session = session
            st.rerun()


# ── STEP 4 — MONITOR ─────────────────────────────────────────────────────────
if st.session_state.created_session:
    st.markdown("---")
    s = st.session_state.created_session
    join_url = s.get("join_url") or s.get("url") or s.get("participant_url", "")
    session_id = s.get("id") or s.get("session_id", "")

    st.subheader("Step 4 — Monitor & Ingest")

    if join_url:
        st.markdown(f"**Participant URL:** [{join_url}]({join_url})")
        st.code(join_url)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Poll Status**")
        if st.button("Refresh Status"):
            with st.spinner("Polling..."):
                try:
                    status = harmonica.get_session(session_id)
                    responses = harmonica.get_responses(session_id)
                    st.metric("Status", status.get("status", "unknown"))
                    st.metric("Responses", len(responses))
                except Exception as e:
                    st.error(str(e))

    with col2:
        st.markdown("**Ingest Results into KG**")
        kengram_id = st.text_input("Kengram ID", key="ingest_kg_id")
        if st.button("Ingest", disabled=not kengram_id):
            from agent import ResultsIngestor
            with st.spinner("Ingesting summary into KG..."):
                try:
                    result = ResultsIngestor(bonfire, harmonica).ingest(session_id, kengram_id)
                    st.success(f"Done — {result['entities_pinned']} entities pinned.")
                except Exception as e:
                    st.error(str(e))
