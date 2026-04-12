import streamlit as st
import pandas as pd
import anthropic
import os

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="FP&A Variance Commentary", layout="wide")
st.title("FP&A Variance Commentary Generator")
st.caption("Upload your budget and actuals files to generate CFO-ready commentary.")

# ── API key (env var on Streamlit Cloud, fallback to manual input locally) ────
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    api_key = st.text_input("Enter your Anthropic API Key", type="password")

# ── File loader — handles CSV and Excel ───────────────────────────────────────
def load_file(uploaded_file):
    """Load CSV or Excel. Returns (dataframe or ExcelFile, sheet_names or None)."""
    if uploaded_file is None:
        return None, None
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file), None
    elif name.endswith((".xlsx", ".xls")):
        xl = pd.ExcelFile(uploaded_file)
        return xl, xl.sheet_names
    else:
        st.error(f"Unsupported file type: {uploaded_file.name}")
        return None, None

# ── File upload ───────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Budget File**")
    budget_file = st.file_uploader("CSV or Excel", type=["csv","xlsx","xls"], key="budget")
with col2:
    st.markdown("**Actuals File**")
    actuals_file = st.file_uploader("CSV or Excel", type=["csv","xlsx","xls"], key="actuals")

# ── Sheet selector (only appears for Excel files) ─────────────────────────────
budget_df = actuals_df = None

if budget_file:
    budget_raw, budget_sheets = load_file(budget_file)
    if budget_sheets:
        selected_budget_sheet = st.selectbox("Select Budget sheet", budget_sheets)
        budget_df = budget_raw.parse(selected_budget_sheet)
    else:
        budget_df = budget_raw

if actuals_file:
    actuals_raw, actuals_sheets = load_file(actuals_file)
    if actuals_sheets:
        selected_actuals_sheet = st.selectbox("Select Actuals sheet", actuals_sheets)
        actuals_df = actuals_raw.parse(selected_actuals_sheet)
    else:
        actuals_df = actuals_raw

# ── Column mapping (appears once both files are loaded) ───────────────────────
dept_col = cat_col = period_cols = None

if budget_df is not None and actuals_df is not None:
    st.divider()
    st.subheader("Column Mapping")
    st.caption("Tell the tool which columns contain what. Period columns = months, quarters, or any numeric columns.")

    all_cols = list(budget_df.columns.astype(str))

    col_a, col_b = st.columns(2)
    with col_a:
        dept_col = st.selectbox(
            "Department / Group column",
            options=all_cols,
            index=all_cols.index("Department") if "Department" in all_cols else 0
        )
    with col_b:
        cat_col = st.selectbox(
            "Category / Line item column (select same as above if not applicable)",
            options=all_cols,
            index=all_cols.index("Category") if "Category" in all_cols else 0
        )

    # Default: everything that isn't dept or cat is a period column
    default_period = [c for c in all_cols if c not in (dept_col, cat_col)]
    period_cols = st.multiselect(
        "Period columns (months, quarters, or totals)",
        options=all_cols,
        default=default_period
    )

    # Preview
    with st.expander("Preview your files (first 5 rows)"):
        st.markdown("**Budget**")
        st.dataframe(budget_df.head(), use_container_width=True)
        st.markdown("**Actuals**")
        st.dataframe(actuals_df.head(), use_container_width=True)

# ── Settings ──────────────────────────────────────────────────────────────────
if budget_df is not None and actuals_df is not None:
    st.divider()
    st.subheader("Settings")
    s1, s2 = st.columns(2)
    with s1:
        materiality_pct = st.slider(
            "Materiality threshold — only flag variances above this %",
            min_value=1, max_value=20, value=5
        )
    with s2:
        audience = st.selectbox(
            "Commentary audience",
            ["CFO", "Board", "Operations Team", "Finance Team"]
        )

# ── Variance math ─────────────────────────────────────────────────────────────
def calculate_variances(budget_df, actuals_df, dept_col, cat_col, period_cols, materiality_pct):
    """
    All math happens here in Python.
    LLM receives only pre-calculated, verified numbers.
    """
    b = budget_df.copy()
    a = actuals_df.copy()

    # Coerce period columns to numeric
    for col in period_cols:
        b[col] = pd.to_numeric(b[col], errors="coerce").fillna(0)
        a[col] = pd.to_numeric(a[col], errors="coerce").fillna(0)

    b["Total_Budget"] = b[period_cols].sum(axis=1)
    a["Total_Actuals"] = a[period_cols].sum(axis=1)

    merge_keys = [dept_col] if dept_col == cat_col else [dept_col, cat_col]

    merged = b[merge_keys + ["Total_Budget"]].merge(
        a[merge_keys + ["Total_Actuals"]],
        on=merge_keys,
        how="outer"
    ).fillna(0)

    merged["Variance_$"] = merged["Total_Actuals"] - merged["Total_Budget"]
    merged["Variance_%"] = (
        merged["Variance_$"] / merged["Total_Budget"].replace(0, float("nan")) * 100
    ).round(1).fillna(0)
    merged["Flag"] = merged["Variance_%"].abs() >= materiality_pct
    merged["Direction"] = merged["Variance_$"].apply(
        lambda x: "Unfavorable" if x > 0 else "Favorable"
    )

    flagged = merged[merged["Flag"]].sort_values("Variance_%", key=abs, ascending=False)
    return merged, flagged

# ── Prompt builder ────────────────────────────────────────────────────────────
def build_prompt(flagged_df, dept_col, cat_col, audience):
    lines = []
    for _, row in flagged_df.iterrows():
        label = f"{row[dept_col]}" if dept_col == cat_col else f"{row[dept_col]} / {row[cat_col]}"
        lines.append(
            f"- {label}: "
            f"Budget ${row['Total_Budget']:,.0f}, "
            f"Actuals ${row['Total_Actuals']:,.0f}, "
            f"Variance ${row['Variance_$']:,.0f} ({row['Variance_%']}%) — {row['Direction']}"
        )

    variance_block = "\n".join(lines)

    return f"""You are a senior FP&A analyst writing a variance commentary for the {audience}.

The following variances have been calculated by our financial system and are mathematically verified.
Do NOT recalculate or second-guess these numbers. Your job is to write clear, professional commentary.

FLAGGED VARIANCES (above materiality threshold):
{variance_block}

Instructions:
1. Write an executive summary (2-3 sentences) of overall budget performance.
2. For each flagged line item, write one concise sentence explaining the variance with a likely business driver.
3. Close with one sentence on recommended management actions.
4. Tone: professional, direct, suitable for {audience}.
5. Write in prose paragraphs — no bullet points.
"""

# ── Generate button ───────────────────────────────────────────────────────────
ready = (
    budget_df is not None and
    actuals_df is not None and
    dept_col and cat_col and period_cols
)

if ready:
    st.divider()
    if st.button("Generate Commentary", type="primary"):
        if not api_key:
            st.error("No API key found. Add it in Streamlit Secrets or enter it above.")
        elif not period_cols:
            st.error("Please select at least one period column.")
        else:
            with st.spinner("Calculating variances..."):
                full_df, flagged_df = calculate_variances(
                    budget_df, actuals_df, dept_col, cat_col, period_cols, materiality_pct
                )

            # Variance table
            st.subheader("Variance Summary")
            merge_keys = [dept_col] if dept_col == cat_col else [dept_col, cat_col]
            display = full_df[merge_keys + ["Total_Budget","Total_Actuals","Variance_$","Variance_%","Direction","Flag"]].copy()

            def highlight_flag(row):
                if row["Flag"] and row["Direction"] == "Unfavorable":
                    return ["background-color: #ffd6d6"] * len(row)
                elif row["Flag"] and row["Direction"] == "Favorable":
                    return ["background-color: #d6f5d6"] * len(row)
                return [""] * len(row)

            st.dataframe(
                display.style.apply(highlight_flag, axis=1).format({
                    "Total_Budget": "${:,.0f}",
                    "Total_Actuals": "${:,.0f}",
                    "Variance_$": "${:,.0f}",
                    "Variance_%": "{:.1f}%"
                }),
                use_container_width=True
            )

            if flagged_df.empty:
                st.info("No variances exceeded the materiality threshold. Try lowering the slider.")
            else:
                with st.spinner("Generating commentary via Claude..."):
                    prompt = build_prompt(flagged_df, dept_col, cat_col, audience)
                    client = anthropic.Anthropic(api_key=api_key)
                    message = client.messages.create(
                        model="claude-opus-4-5",
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    commentary = message.content[0].text

                st.subheader("Generated Commentary")
                st.write(commentary)
                st.text_area(
                    "Copy-ready version",
                    value=commentary,
                    height=300
                )
                st.caption("Copy and paste directly into your board pack or reporting email.")
