import streamlit as st


def render_settings(config):
    """Page: Edit config values, manage API keys, toggle automation."""
    st.header("Settings")

    # AI Provider
    st.subheader("AI Provider")
    provider = st.selectbox(
        "Provider",
        ["openai", "anthropic"],
        index=0 if config.ai.provider == "openai" else 1,
        key="settings_provider",
    )
    if provider == "openai":
        api_key = config.ai.openai.api_key
        masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "Not set"
        st.text_input("OpenAI API Key", value=masked, disabled=True)
        st.caption(f"Model: {config.ai.openai.model}")
    else:
        api_key = config.ai.anthropic.api_key
        masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "Not set"
        st.text_input("Anthropic API Key", value=masked, disabled=True)
        st.caption(f"Model: {config.ai.anthropic.model}")

    st.divider()

    # Scheduling
    st.subheader("Scheduling")
    st.caption(f"Timezone: **{config.scheduling.timezone}**")
    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"Post hours: **{config.scheduling.posts.cron_hour}**")
        st.caption(f"Max posts/day: **{config.scheduling.posts.max_per_day}**")
    with col2:
        st.caption(f"Comment interval: **{config.scheduling.comments.interval_hours}h**")
        st.caption(f"Active hours: **{config.scheduling.comments.active_start_hour}-{config.scheduling.comments.active_end_hour}**")
        st.caption(f"Max comments/day: **{config.scheduling.comments.max_per_day}**")

    st.divider()

    # Safety
    st.subheader("Safety Limits")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"Hourly: **{config.safety.hourly_action_limit}**")
    with col2:
        st.caption(f"Daily: **{config.safety.daily_action_limit}**")
    with col3:
        st.caption(f"Weekly: **{config.safety.weekly_action_limit}**")
    st.caption(f"Error threshold: **{config.safety.error_rate_threshold:.0%}**")
    st.caption(f"Cooldown: **{config.safety.cooldown_minutes} min**")

    st.divider()

    # LinkedIn
    st.subheader("LinkedIn")
    email = config.linkedin.email
    st.caption(f"Account: **{email or 'Not configured'}**")
    st.caption(f"Headless: **{config.linkedin.headless}**")
    st.caption(f"Profile dir: **{config.linkedin.browser_profile_dir}**")

    st.divider()
    st.info("To change settings, edit `config/config.yaml` and `.env`, then restart the app.")
