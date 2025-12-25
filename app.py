import streamlit as st
import pandas as pd
import io

# 设置网页标题
st.set_page_config(page_title="首提助力金自动结算系统", page_icon="💰")

st.title("💰 首提助力金 - 自动化结算工具 (整数奖励版)")
st.markdown("### 逻辑：[自动汇总订单] -> 筛选 [0提现] 且 [余额<2000] -> 计算 20% (取整)")

# --- 文件上传区 ---
col1, col2 = st.columns(2)
with col1:
    st.info("步骤 1：上传代收订单")
    file_orders = st.file_uploader("请上传代收订单.csv", type=['csv', 'xlsx'], key="order")

with col2:
    st.info("步骤 2：上传用户列表")
    file_users = st.file_uploader("请上传用户列表.csv", type=['csv', 'xlsx'], key="user")

# --- 核心处理逻辑 ---
if file_orders and file_users:
    try:
        # 1. 读取文件
        if file_orders.name.endswith('.csv'):
            df_orders = pd.read_csv(file_orders)
        else:
            df_orders = pd.read_excel(file_orders)

        if file_users.name.endswith('.csv'):
            df_users = pd.read_csv(file_users)
        else:
            df_users = pd.read_excel(file_users)

        # 强力去重列名
        df_orders = df_orders.loc[:, ~df_orders.columns.duplicated()]
        df_users = df_users.loc[:, ~df_users.columns.duplicated()]

        # 去除列名的空格
        df_orders.columns = df_orders.columns.str.strip()
        df_users.columns = df_users.columns.str.strip()

        st.success(f"文件读取成功！订单表: {len(df_orders)} 行，用户表: {len(df_users)} 行")

        # ==========================================
        # 🛠️ 字段映射配置
        # ==========================================
        COL_ORDER_UID = '用户ID'
        COL_ORDER_AMOUNT = '用户付款金额' 

        COL_USER_UID = '用户ID'
        COL_USER_BALANCE = '账户余额'
        COL_USER_WITHDRAW_COUNT = '提现次数'
        COL_USER_CUSTOM_ACC = '自定义账号'

        # ==========================================
        # 🛠️ 检查字段
        # ==========================================
        missing_cols = []
        if COL_ORDER_UID not in df_orders.columns: missing_cols.append(f"订单表-{COL_ORDER_UID}")
        if COL_ORDER_AMOUNT not in df_orders.columns: missing_cols.append(f"订单表-{COL_ORDER_AMOUNT}")
        if COL_USER_UID not in df_users.columns: missing_cols.append(f"用户表-{COL_USER_UID}")
        if COL_USER_BALANCE not in df_users.columns: missing_cols.append(f"用户表-{COL_USER_BALANCE}")
        if COL_USER_WITHDRAW_COUNT not in df_users.columns: missing_cols.append(f"用户表-{COL_USER_WITHDRAW_COUNT}")

        if missing_cols:
            st.error(f"❌ 表格中缺少以下关键列：\n{', '.join(missing_cols)}")
            st.stop()

        # ==========================================
        # 🛠️ 数据清洗
        # ==========================================
        def clean_currency(x):
            if isinstance(x, str):
                return pd.to_numeric(x.replace(',', '').strip(), errors='coerce')
            return x

        df_orders[COL_ORDER_AMOUNT] = df_orders[COL_ORDER_AMOUNT].apply(clean_currency)
        df_users[COL_USER_BALANCE] = df_users[COL_USER_BALANCE].apply(clean_currency)
        df_users[COL_USER_WITHDRAW_COUNT] = pd.to_numeric(df_users[COL_USER_WITHDRAW_COUNT], errors='coerce').fillna(0)

        def clean_id(x):
            s = str(x).strip()
            if s.endswith('.0'): 
                return s[:-2]
            return s

        df_orders[COL_ORDER_UID] = df_orders[COL_ORDER_UID].apply(clean_id)
        df_users[COL_USER_UID] = df_users[COL_USER_UID].apply(clean_id)

        # ==========================================
        # 🛠️ 核心计算
        # ==========================================
        
        # 1. 自动汇总订单
        df_orders_agg = df_orders.groupby(COL_ORDER_UID, as_index=False)[COL_ORDER_AMOUNT].sum()
        df_orders_agg = df_orders_agg.rename(columns={COL_ORDER_AMOUNT: '本次时段总充值'})
        
        # 2. 数据合并
        merged_df = pd.merge(df_orders_agg, df_users, left_on=COL_ORDER_UID, right_on=COL_USER_UID, how='inner')

        # 3. 规则筛选
        result_df = merged_df[
            (merged_df[COL_USER_WITHDRAW_COUNT] == 0) & 
            (merged_df[COL_USER_BALANCE] < 2000)
        ].copy()

        # 4. 计算奖励 (强制取整)
        # 先算乘法，然后 .astype(int) 会直接去掉小数部分
        result_df['应发奖励'] = (result_df['本次时段总充值'] * 0.20).astype(int)

        # ==========================================
        # 🛠️ 输出结果
        # ==========================================
        
        cols_to_show = [COL_USER_UID, '本次时段总充值', COL_USER_BALANCE, COL_USER_WITHDRAW_COUNT, '应发奖励']
        if COL_USER_CUSTOM_ACC in result_df.columns:
            cols_to_show.insert(1, COL_USER_CUSTOM_ACC)
        
        final_output = result_df[cols_to_show]
        
        st.divider()
        if len(final_output) > 0:
            st.subheader(f"✅ 计算完成！共发现 {len(final_output)} 位符合条件的用户")
            
            # 格式化展示: {:,.0f} 表示不保留小数
            st.dataframe(final_output.style.format({
                "本次时段总充值": "{:,.0f}", 
                COL_USER_BALANCE: "{:,.0f}", 
                "应发奖励": "{:,.0f}",  
                COL_USER_WITHDRAW_COUNT: "{:.0f}"
            }))
            
            total_payout = final_output['应发奖励'].sum()
            st.metric(label="预计总派发金额", value=f"{total_payout:,.0f}")

            # 下载按钮
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_output.to_excel(writer, index=False, sheet_name='派发名单')
            
            st.download_button(
                label="📥 下载派发名单 (Excel)",
                data=output.getvalue(),
                file_name="首提助力金_整数版.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("⚠️ 没有发现符合条件的用户。")

    except Exception as e:
        st.error(f"发生程序错误: {e}")

else:
    st.info("请在上方上传两个表格...")