"""🤖 AI Coach — personalized training recommendations via LLM."""

from __future__ import annotations


import pandas as pd
import streamlit as st

from hevy.llm.advisor import TrainingAdvisor
from hevy.llm.providers import LLMProvider
from hevy.llm.history import ConversationStore
from hevy.llm.prompts import build_analysis_prompt, build_focus_prompt, COACH_SYSTEM_PROMPT
from hevy.client import HevyClient


def render(
    sets_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    templates_df: pd.DataFrame,
    measurements_df: pd.DataFrame,
    routines_df_raw: pd.DataFrame,
    **_,
) -> None:
    st.title("🤖 AI Coach")
    st.markdown("Get personalized training recommendations powered by Deepseek AI.")

    if not summary_df.empty:
        data_start = pd.to_datetime(summary_df["start_time"]).min().strftime("%b %d, %Y")
        data_end = pd.to_datetime(summary_df["start_time"]).max().strftime("%b %d, %Y")
        st.info(
            f"📅 Analyzing **{len(summary_df)} workouts** from **{data_start} → {data_end}** "
            f"({len(sets_df)} sets). Use the sidebar date filter to narrow the time range."
        )
    else:
        st.warning("No workouts in the selected date range. Adjust the sidebar filter.")
        return

    # Routine selector
    st.markdown("### 📋 Your Routines")
    if not routines_df_raw.empty:
        all_routines = sorted(routines_df_raw["routine_title"].unique())
        selected_routines = st.multiselect(
            "Select routines to include in the analysis",
            options=all_routines, default=all_routines,
            help="Choose which routines the AI Coach should know about.",
        )
        routines_df = routines_df_raw[routines_df_raw["routine_title"].isin(selected_routines)].copy() if selected_routines else pd.DataFrame()
    else:
        routines_df = pd.DataFrame()
        st.caption("No routines found.")

    st.markdown("---")

    # Provider config
    col1, col2 = st.columns([2, 1])
    with col1:
        llm_provider = st.selectbox("LLM Provider", ["deepseek", "openai", "ollama"], key="ai_provider")
    with col2:
        api_key = st.text_input("API Key (optional)", type="password", key="ai_api_key",
                                help="Leave blank to use the environment variable.")

    provider_args = {"provider": llm_provider}
    if api_key:
        provider_args["api_key"] = api_key

    llm_available = True
    try:
        test_provider = LLMProvider(**provider_args)
        test_provider.close()
    except (ValueError, PermissionError) as e:
        llm_available = False
        st.warning(f"⚠️ {e}")

    # Conversation state
    conv_store = ConversationStore()
    if "ai_conversation" not in st.session_state:
        st.session_state.ai_conversation = []
    if "ai_metadata" not in st.session_state:
        st.session_state.ai_metadata = {"goals": "", "focus": "", "label": ""}

    def _auto_save_conv(label_suffix: str = "") -> None:
        if not st.session_state.ai_conversation:
            return
        st.session_state.ai_metadata["label"] = (
            f"{st.session_state.ai_metadata.get('goals', '')[:40]} {label_suffix}".strip()
        )
        conv_store.save_conversation(st.session_state.ai_conversation, metadata=st.session_state.ai_metadata)

    def _call_llm(system_prompt: str, user_message: str, conversation: list | None = None, max_tokens: int = 8192) -> str | None:
        messages = list(conversation or [])
        messages.append({"role": "user", "content": user_message})
        try:
            provider = LLMProvider(**provider_args, max_tokens=max_tokens)
            resp = provider.chat(messages=messages, system_prompt=system_prompt)
            provider.close()
            st.caption(f"Model: {resp.model} · {resp.input_tokens:,} in · {resp.output_tokens:,} out")
            return resp.content
        except Exception as e:
            st.error(f"Error: {e}")
            return None

    # Conversation history sidebar
    with st.sidebar:
        with st.expander("💬 Conversation History", expanded=False):
            conversations = conv_store.list_conversations(limit=15)
            if conversations:
                for c in conversations:
                    label = c["label"][:35] if c["label"] else "Untitled"
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        if st.button(f"{label} ({c['messages']} msgs)", key=f"load_{c['path']}"):
                            loaded = conv_store.load_conversation(c["path"])
                            if loaded:
                                st.session_state.ai_conversation = loaded
                                st.rerun()
                    with col2:
                        if st.button("🗑️", key=f"del_{c['path']}"):
                            conv_store.delete_conversation(c["path"])
                            st.rerun()
            if st.session_state.ai_conversation:
                if st.button("💾 Save Current", key="save_current_conv"):
                    conv_store.save_conversation(st.session_state.ai_conversation, metadata=st.session_state.get("ai_metadata", {}))
                    st.success("Saved!")
                    st.rerun()

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Full Analysis", "🎯 Focus Area", "💬 Free Question"])

    with tab1:
        default_goals = st.session_state.ai_metadata.get("goals",
            "General hypertrophy and strength. I want to improve my physique symmetry and address weak points.")
        goals = st.text_area("Your training goals", value=default_goals, height=100, key="tab1_goals",
                             on_change=lambda: st.session_state.ai_metadata.update({"goals": st.session_state.tab1_goals}))
        if st.button("🚀 Analyze My Training", type="primary", key="tab1_btn", disabled=not llm_available):
            if llm_available:
                with st.spinner("Analyzing your training data... may take 10-30s."):
                    advisor = TrainingAdvisor(sets_df, summary_df, templates_df, measurements_df, routines_df=routines_df)
                    stats = advisor.get_snapshot()
                    prompt = build_analysis_prompt(
                        stats=stats["stats"], muscle_balance=stats["muscle_balance"],
                        head_balance=stats["head_balance"], recent_trends=stats["trends"],
                        goals=goals, routines_summary=advisor._format_routines(),
                    )
                    response = _call_llm(COACH_SYSTEM_PROMPT, prompt, max_tokens=16384)
                    if response:
                        st.session_state.ai_conversation = [{"role": "assistant", "content": response}]
                        _auto_save_conv("analysis")
                        st.rerun()

    with tab2:
        focus_areas = [
            "Overall symmetry and balance", "Chest (upper/middle/lower)", "Triceps (all heads)",
            "Shoulders (anterior/lateral/posterior)", "Back width and thickness",
            "Legs (quads/hams/glutes)", "Core and abs", "Posterior chain (deadlift focus)",
            "Arms (biceps and triceps)", "Fix left/right imbalances",
        ]
        focus = st.selectbox("What area to improve?", focus_areas, key="tab2_focus")
        focus_goals = st.text_input("Specific goals?", value=f"Build more {focus.lower()}", key="tab2_goals")
        if st.button("🎯 Get Focused Advice", type="primary", key="tab2_btn", disabled=not llm_available):
            if llm_available:
                with st.spinner(f"Getting advice on {focus}..."):
                    advisor = TrainingAdvisor(sets_df, summary_df, templates_df, measurements_df, routines_df=routines_df)
                    stats = advisor._build_stats()
                    head_bal = advisor._build_head_balance()
                    prompt = build_focus_prompt(f"{focus}: {focus_goals}", stats, head_bal)
                    response = _call_llm(COACH_SYSTEM_PROMPT, prompt, max_tokens=8192)
                    if response:
                        st.session_state.ai_conversation = [{"role": "assistant", "content": response}]
                        _auto_save_conv("focus")
                        st.rerun()

    with tab3:
        question = st.text_area("Your question",
            value="What's the one thing I should change in my current routine to see the biggest improvement?",
            height=100, key="tab3_q")
        if st.button("💬 Ask", type="primary", key="tab3_btn", disabled=not llm_available):
            if llm_available:
                with st.spinner("Thinking..."):
                    advisor = TrainingAdvisor(sets_df, summary_df, templates_df, measurements_df, routines_df=routines_df)
                    context = advisor._quick_stats_summary()
                    response = _call_llm(COACH_SYSTEM_PROMPT,
                        f"Here is my training data summary:\n{context}\n\nMy question is: {question}", max_tokens=8192)
                    if response:
                        st.session_state.ai_conversation = [{"role": "assistant", "content": response}]
                        _auto_save_conv("question")
                        st.rerun()

    # Conversation display + follow-up
    st.markdown("---")
    if st.session_state.ai_conversation:
        for msg in st.session_state.ai_conversation:
            if msg["role"] == "assistant":
                with st.chat_message("assistant"):
                    from hevy.llm.implement import extract_and_push_routine
                    st.markdown(msg["content"])
                    last_response = msg["content"]
                    if st.button("🔄 Implement as Routine", key="implement_routine", type="secondary"):
                        with st.spinner("Extracting and pushing routine to Hevy..."):
                            try:
                                client = HevyClient()
                                result = extract_and_push_routine(last_response, sets_df, templates_df, client)
                                if result["success"]:
                                    st.success(f"✅ Routine '{result['routine_title']}' pushed to Hevy!")
                                    for msg_text in result.get("messages", []):
                                        st.info(msg_text)
                                else:
                                    st.error(f"Failed: {result.get('error', 'Unknown error')}")
                            except Exception as e:
                                st.error(f"Error: {e}")

        prompt = st.chat_input("Ask a follow-up question...")
        if prompt:
            conversation = st.session_state.ai_conversation[-6:]
            response = _call_llm(COACH_SYSTEM_PROMPT, prompt, conversation=conversation)
            if response:
                st.session_state.ai_conversation.append({"role": "user", "content": prompt})
                st.session_state.ai_conversation.append({"role": "assistant", "content": response})
                _auto_save_conv("followup")
                st.rerun()
    else:
        st.info("Use one of the tabs above to start a conversation with the AI Coach.")

    # Clear button
    if st.session_state.ai_conversation:
        if st.button("🗑️ Clear conversation", type="secondary"):
            st.session_state.ai_conversation = []
            st.rerun()
