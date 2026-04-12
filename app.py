import streamlit as st
import pandas as pd
import anthropic

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="FP&A Variance Commentary", layout="wide")
st.title("FP&A Variance Commentary Generator")
st.caption("Upload your budget and actuals CSVs to generate CFO-ready commentary.")

# ── API key input ─────────────────────────────────────────────────────────────
api_key = st.text_input("Enter your Anthropic API Key", type="password")

# ── File upload ───────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    budget_file = st.file_uploader("Upload Budget CSV", type="csv")
with col2:
    actuals_file = st.file_uploader("Upload Actuals CSV", type="csv")

# ── Settings ──────────────────────────────────────────────────────────────────
materiality_pct = st.slider(
    "Materiality threshold (only flag variances above this %)",
    min_value=1, max_value=20, value=5
)
audience = st.selectbox("Commentary audience", ["CFO", "Board", "Operations Team"])

# ── Core logic ────────────────────────────────────────────────────────────────
def calculate_variances(budget_df, actuals_df, materiality_pct):
    """
    Do all the math in Python — never let the LLM touch raw numbers.
    Returns a list of flagged variance dicts above the materiality threshold.
    """
    # Sum across all months for each Department + Category row
    month_cols = [c for c in budget_df.columns if c not in ("Department", "Category")]

    budget_df["Total_Budget"] = budget_df[month_cols].sum(axis=1)
    actuals_df["Total_Actuals"] = actuals_df[month_cols].sum(axis=1)

    merged = budget_df[["Department", "Category", "Total_Budget"]].merge(
        actuals_df[["Department", "Category", "Total_Actuals"]],
        on=["Department", "Category"]
    )

    merged["Variance_$"] = merged["Total_Actuals"] - merged["Total_Budget"]
    merged["Variance_%"] = (merged["Variance_$"] / merged["Total_Budget"] * 100).round(1)
    merged["Flag"] = merged["Variance_%"].abs() >= materiality_pct
    merged["Direction"] = merged["Variance_$"].apply(
        lambda x: "Unfavorable" if x > 0 else "Favorable"
    )

    flagged = merged[merged["Flag"]].sort_values("Variance_%", key=abs, ascending=False)
    return merged, flagged

def build_prompt(flagged_df, audience):
    """
    Structured prompt — pass verified numbers, ask for language only.
    """
    lines = []
    for _, row in flagged_df.iterrows():
        lines.append(
            f"- {row['Department']} / {row['Category']}: "
            f"Budget ${row['Total_Budget']:,.0f}, "
            f"Actuals ${row['Total_Actuals']:,.0f}, "
            f"Variance ${row['Variance_$']:,.0f} ({row['Variance_%']}%) — {row['Direction']}"
        )

    variance_block = "\n".join(lines)

    prompt = f"""You are a senior FP&A analyst writing a variance commentary for the {audience}.

The following variances have been calculated by our financial system and are mathematically verified.
Do NOT recalculate or second-guess these numbers. Your job is to write clear, professional commentary.

FLAGGED VARIANCES (above materiality threshold):
{variance_block}

Instructions:
1. Write an executive summary (2-3 sentences) of overall budget performance.
2. For each flagged line item, write one concise sentence explaining the variance with a likely business driver.
3. Close with one sentence on recommended management actions.
4. Tone: professional, direct, suitable for {audience}.
5. Do not use bullet points — write in prose paragraphs.
"""
    return prompt

# ── Run button ────────────────────────────────────────────────────────────────
if st.button("Generate Commentary", type="primary"):
    if not api_key:
        st.error("Please enter your Anthropic API key.")
    elif budget_file is None or actuals_file is None:
        st.error("Please upload both CSV files.")
    else:
        with st.spinner("Calculating variances..."):
            budget_df = pd.read_csv(budget_file)
            actuals_df = pd.read_csv(actuals_file)
            full_df, flagged_df = calculate_variances(budget_df, actuals_df, materiality_pct)

        # Show variance table
        st.subheader("Variance Summary")
        display = full_df[["Department","Category","Total_Budget","Total_Actuals","Variance_$","Variance_%","Direction","Flag"]].copy()
        display.columns = ["Dept","Category","Budget","Actuals","Variance $","Variance %","Direction","Flagged"]

        def highlight_flag(row):
            if row["Flagged"] and row["Direction"] == "Unfavorable":
                return ["background-color: #ffd6d6"] * len(row)
            elif row["Flagged"] and row["Direction"] == "Favorable":
                return ["background-color: #d6f5d6"] * len(row)
            return [""] * len(row)

        st.dataframe(
            display.style.apply(highlight_flag, axis=1).format({
                "Budget": "${:,.0f}",
                "Actuals": "${:,.0f}",
                "Variance $": "${:,.0f}",
                "Variance %": "{:.1f}%"
            }),
            use_container_width=True
        )

        if flagged_df.empty:
            st.info("No variances exceeded the materiality threshold.")
        else:
            with st.spinner("Generating commentary via Claude..."):
                prompt = build_prompt(flagged_df, audience)
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}]
                )
                commentary = message.content[0].text

            st.subheader("Generated Commentary")
            st.write(commentary)
            st.code(commentary, language=None)
            st.caption("Copy the text above and paste directly into your board pack or email.")
