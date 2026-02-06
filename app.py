import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from fpdf import FPDF
import altair as alt
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Akıllı Aşı Lojistik Paneli", layout="wide")

st.title("💉 Akıllı Aşı Talep Tahmini ve Stok Yönetim Paneli")

# --- YARDIMCI FONKSİYONLAR ---
def clean_number(x):
    if isinstance(x, str):
        return x.replace('.', '').replace(',', '').replace('"', '').strip()
    return x

def get_dates_from_csv(file):
    try:
        file.seek(0)
        try:
            lines = [file.readline().decode('utf-8') for _ in range(15)]
        except:
            file.seek(0)
            lines = [file.readline().decode('iso-8859-9') for _ in range(15)]
            
        file.seek(0)
        start_date, end_date = None, None
        date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')
        
        for line in lines:
            if "Baslangiç Tarihi" in line:
                match = date_pattern.search(line)
                if match:
                    start_date = match.group()
            if "Bitis Tarihi" in line:
                match = date_pattern.search(line)
                if match:
                    end_date = match.group()
                    
        if start_date and end_date:
            d1 = datetime.strptime(start_date, "%d.%m.%Y")
            d2 = datetime.strptime(end_date, "%d.%m.%Y")
            diff = (d2 - d1).days + 1
            return diff, start_date, end_date
    except Exception:
        pass
    return 91, None, None

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Rapor')
    return output.getvalue()

def tr_fix(text):
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("🚨", "").replace("✅", "").replace("⚠️", "")
    rep = {"İ":"I","ı":"i","Ğ":"G","ğ":"g","Ş":"S","ş":"s","ç":"c","Ç":"C","ö":"o","Ö":"O","ü":"u","Ü":"U"}
    for k, v in rep.items():
        text = text.replace(k, v)
    return text.strip()

def to_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, tr_fix(title), ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 8)
    cols = df.columns.tolist()
    col_width = 190 / len(cols)
    
    for col in cols:
        pdf.cell(col_width, 8, tr_fix(str(col)), 1)
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 7)
    for i in range(len(df)):
        for col in cols:
            val = tr_fix(str(df.iloc[i][col]))
            pdf.cell(col_width, 7, val[:25], 1)
        pdf.ln()
    
    return bytes(pdf.output())

# --- YAN MENÜ: KOMPAKT AYARLAR ---
st.sidebar.markdown("### ⚙️ Ayarlar")

plan_suresi = st.sidebar.slider("Plan Süresi (Gün)", 7, 90, 15)
guvenlik_marji = st.sidebar.slider("Güvenlik Payı (%)", 0, 100, 20) / 100

c1, c2 = st.sidebar.columns(2)
with c1:
    kritik_esik = st.number_input("Kritik (Gün)", value=3)
with c2:
    asiri_esik = st.number_input("Aşırı (Gün)", value=60)

# --- DOSYA YÜKLEME ALANI ---
col_u1, col_u2 = st.columns(2)
with col_u1:
    tuketim_file = st.file_uploader("📂 Dönemsel Tüketim Raporu (CSV)", type=["csv"])
with col_u2:
    stok_file = st.file_uploader("📂 Stok Durum Raporu Birim Bazında (CSV)", type=["csv"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file:
    try:
        oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_csv(tuketim_file)
        
        # --- GÜÇLENDİRİLMİŞ CSV OKUMA ---
        def robust_read_csv(file, header_row):
            methods = [
                {'encoding': 'utf-8', 'sep': ';'},
                {'encoding': 'iso-8859-9', 'sep': ';'},
                {'encoding': 'utf-8', 'sep': ','},
                {'encoding': 'iso-8859-9', 'sep': ','},
                {'encoding': 'iso-8859-9', 'sep': ';', 'quoting': 3, 'on_bad_lines': 'skip'},
                {'encoding': 'iso-8859-9', 'sep': ',', 'quoting': 3, 'on_bad_lines': 'skip'},
                {'encoding': 'utf-8', 'sep': None, 'engine': 'python'}
            ]
            
            for m in methods:
                try:
                    file.seek(0)
                    kw = {k: v for k, v in m.items() if k != 'encoding'}
                    df = pd.read_csv(file, header=header_row, encoding=m['encoding'], dtype=str, **kw)
                    if len(df.columns) < 2: continue
                    return df
                except Exception:
                    continue
            
            file.seek(0)
            return pd.read_csv(file, header=header_row, encoding='iso-8859-9', sep=';', dtype=str, on_bad_lines='skip')

        df_raw_t = robust_read_csv(tuketim_file, 7)
        df_raw_s = robust_read_csv(stok_file, 3)
        
        # Temizlik
        df_raw_t.columns = [c.strip() for c in df_raw_t.columns]
        df_raw_s.columns = [c.strip() for c in df_raw_s.columns]

        # --- AKILLI SÜTUN ONARICI ---
        def smart_fix_columns(df):
            rename_map = {}
            for col in df.columns:
                col_upper = col.upper()
                col_clean = col.replace('"', '').strip()
                if 'ZAYI' in col_upper: rename_map[col] = 'ZAYI'
                elif (col_upper.startswith('IL') or col_upper.startswith('İL')) and col_upper.endswith('E'): rename_map[col] = 'ILÇE'
                elif 'BIRIM' in col_upper and 'ADI' in col_upper: rename_map[col] = 'BIRIM ADI'
                elif 'BIRIM' in col_upper and 'TIPI' in col_upper: rename_map[col] = 'BIRIM TIPI'
                elif 'TAN' in col_upper and 'IMI' in col_upper: rename_map[col] = 'ÜRÜN TANIMI'
                elif 'TOPLAM' in col_upper and 'DOZ' in col_upper and 'UYGULANAN' not in col_upper and 'ZAYI' not in col_upper: rename_map[col] = 'TOPLAM DOZ'
            if rename_map: df.rename(columns=rename_map, inplace=True)
            return df

        df_raw_s = smart_fix_columns(df_raw_s)
        df_raw_t = smart_fix_columns(df_raw_t)
        
        if 'BIRIM ADI' in df_raw_s.columns: df_raw_s.rename(columns={'BIRIM ADI': 'BIRIM'}, inplace=True)

        # Veri Doldurma
        df_raw_t[['ILÇE', 'BIRIM']] = df_raw_t[['ILÇE', 'BIRIM']].ffill()
        df_raw_s[['ILÇE', 'BIRIM', 'BIRIM TIPI']] = df_raw_s[['ILÇE', 'BIRIM', 'BIRIM TIPI']].ffill()
        
        # Sayısal Dönüşümler
        df_raw_t['Tuketim'] = pd.to_numeric(df_raw_t['UYGULANAN DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0)
        df_raw_t['Zayi'] = pd.to_numeric(df_raw_t['ZAYI'].astype(str).apply(clean_number), errors='coerce').fillna(0) if 'ZAYI' in df_raw_t.columns else 0

        stok_col = 'TOPLAM DOZ' if 'TOPLAM DOZ' in df_raw_s.columns else df_raw_s.columns[-1]
        df_raw_s['Stok'] = pd.to_numeric(df_raw_s[stok_col].astype(str).apply(clean_number), errors='coerce').fillna(0)

        # --- KRİTİK AYRIŞTIRMA ---
        mask_ism_stok = (df_raw_s['ILÇE'].str.contains('FATIH', case=False, na=False)) & (df_raw_s['BIRIM'].str.contains('ISM', case=False, na=False))
        mask_ism_tuketim = (df_raw_t['ILÇE'].str.contains('FATIH', case=False, na=False)) & (df_raw_t['BIRIM'].str.contains('ISM', case=False, na=False))

        df_s_saha = df_raw_s[~mask_ism_stok].copy()
        df_t_saha = df_raw_t[~mask_ism_tuketim].copy()
        df_s_ism = df_raw_s[mask_ism_stok].copy()
        df_t_ism = df_raw_t[mask_ism_tuketim].copy()

        # --- MERGE VE HESAPLAMA ---
        df_c = df_t_saha.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI']).agg({'Tuketim': 'sum', 'Zayi': 'sum'}).reset_index()
        df_c.columns = ['Ilce', 'Birim', 'Urun', 'Tuketim', 'Zayi']
        
        df_s_grp = df_s_saha.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI', 'BIRIM TIPI'])['Stok'].sum().reset_index()
        df_s_grp.columns = ['Ilce', 'Birim', 'Urun', 'Tip', 'Stok']
        
        res_df = pd.merge(df_c, df_s_grp, on=['Ilce', 'Birim', 'Urun'], how='outer').fillna(0)
        res_df['Tip'] = res_df['Tip'].replace(0, 'Bilinmiyor')

        res_df['Gunluk_Hiz'] = res_df['Tuketim'] / oto_gun_sayisi
        res_df['Ihtiyac'] = ((res_df['Gunluk_Hiz'] * plan_suresi) * (1 + guvenlik_marji)) - res_df['Stok']
        res_df['Gonderilecek'] = res_df['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
        res_df['Yetme_Suresi'] = res_df.apply(lambda r: round(r['Stok'] / r['Gunluk_Hiz'], 1) if r['Gunluk_Hiz'] > 0 else 999, axis=1)

        def get_durum_ve_fazla(row):
            if row['Yetme_Suresi'] < kritik_esik: durum = "🚨 KRİTİK"
            elif row['Yetme_Suresi'] > asiri_esik:
                tip_str = str(row['Tip']).upper()
                durum = "⚠️ AŞIRI" if any(x in tip_str for x in ['ASM', 'SON KULLANICI']) else "✅ Yeterli"
            else: durum = "✅ Yeterli"
            
            hedef_stok = row['Gunluk_Hiz'] * asiri_esik
            fazla_miktar = max(0, row['Stok'] - hedef_stok)
            return pd.Series([durum, int(fazla_miktar)])

        res_df[['Durum', 'Fazla_Miktar']] = res_df.apply(get_durum_ve_fazla, axis=1)

        # --- FİLTRELER ---
        sec_ilce = st.sidebar.multiselect("📍 İlçe Filtrele", options=sorted(res_df['Ilce'].unique()))
        sec_asi = st.sidebar.multiselect("💉 Aşı Filtrele", options=sorted(res_df['Urun'].unique()))
        
        df_f = res_df.copy()
        if sec_ilce: df_f = df_f[df_f['Ilce'].isin(sec_ilce)]
        if sec_asi: df_f = df_f[df_f['Urun'].isin(sec_asi)]

        st.markdown("---")
        if s_tarih: st.info(f"📅 **Dönemsel Tüketim Raporu:** {s_tarih} - {b_tarih} ({oto_gun_sayisi} Gün)")

        toplam_sevk = int(df_f[df_f['Gonderilecek'] > 0]['Gonderilecek'].sum())
        kritik_sayisi = len(df_f[df_f['Durum'] == "🚨 KRİTİK"])
        asiri_sayisi = len(df_f[df_f['Durum'] == "⚠️ AŞIRI"])
        kurum_sayisi = df_f[df_f['Gonderilecek'] > 0]['Birim'].nunique()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📦 SEVKİYAT (DOZ)", f"{toplam_sevk:,}".replace(",", "."))
        m2.metric("🚨 KRİTİK STOK", kritik_sayisi)
        m3.metric("⚠️ AŞIRI STOK", asiri_sayisi)
        m4.metric("🏢 KURUM SAYISI", kurum_sayisi)
        
        st.markdown("---")

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📦 Sevkiyat Planı", "⚠️ Fazla ve Ölü Stok", "📍 İlçe Bazlı Özet", 
            "📊 İl Geneli", "📉 Zayi ve Verimlilik", "🔄 Akıllı Transfer"
        ])

        with tab1:
            st.caption("Aşağıdaki liste sadece aşı gönderilmesi gereken (İhtiyaç > 0) kurumları içerir.")
            f1_sevk = df_f[df_f['Gonderilecek'] > 0].copy()
            durum_sirasi = {"🚨 KRİTİK": 0, "✅ Yeterli": 1, "⚠️ AŞIRI": 2}
            f1_sevk['sort_key'] = f1_sevk['Durum'].map(durum_sirasi)
            f1_sevk = f1_sevk.sort_values(['sort_key', 'Gonderilecek'], ascending=[True, False]).drop('sort_key', axis=1)
            st.dataframe(f1_sevk[['Durum', 'Ilce', 'Birim', 'Urun', 'Tuketim', 'Stok', 'Gonderilecek', 'Yetme_Suresi']], use_container_width=True)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Sevkiyat Excel", to_excel(f1_sevk), "sevkiyat_plani.xlsx")
            with c2: st.download_button("📥 Sevkiyat PDF", to_pdf(f1_sevk, "Sevkiyat Plani"), "sevkiyat_plani.pdf")

        with tab2:
            st.caption(f"Aşağıdaki liste, {asiri_esik} günden fazla stoğu bulunan ve 'Aşırı' olarak işaretlenen **ASM ve Son Kullanıcı** birimlerini içerir. (TSM ve İSM depoları hariç tutulmuştur)")
            f1_asiri = df_f[df_f['Durum'] == "⚠️ AŞIRI"].copy().sort_values('Yetme_Suresi', ascending=False)
            st.dataframe(f1_asiri[['Ilce', 'Birim', 'Urun', 'Stok', 'Yetme_Suresi']], use_container_width=True)
            c3, c4 = st.columns(2)
            with c3: st.download_button("📥 İade Excel", to_excel(f1_asiri), "asiri_stok.xlsx")
            with c4: st.download_button("📥 İade PDF", to_pdf(f1_asiri, "Asiri Stok"), "asiri_stok.pdf")
            
            st.markdown("---")
            st.subheader("🕸️ Ölü Stok (Hiç Tüketimi Olmayan)")
            f1_olu = df_f[(df_f['Stok'] > 0) & (df_f['Tuketim'] == 0) & (df_f['Tip'].astype(str).str.upper().apply(lambda x: any(k in x for k in ['ASM', 'SON KULLANICI'])))].copy().sort_values('Stok', ascending=False)
            if not f1_olu.empty:
                st.dataframe(f1_olu[['Ilce', 'Birim', 'Urun', 'Stok']], use_container_width=True)
                c_olu1, c_olu2 = st.columns(2)
                with c_olu1: st.download_button("📥 Ölü Stok Excel", to_excel(f1_olu), "olu_stok.xlsx")
                with c_olu2: st.download_button("📥 Ölü Stok PDF", to_pdf(f1_olu, "Olu Stok"), "olu_stok.pdf")
            else: st.success("Tebrikler! Ölü stok (hareketsiz ürün) bulunamadı.")

        with tab3:
            df_i = df_f.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            df_i['Ihtiyac'] = (((df_i['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df_i['Stok']
            df_i['Gonderilecek'] = df_i['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
            f2_visible = df_i[df_i['Gonderilecek'] > 0].copy().sort_values(['Ilce', 'Gonderilecek'], ascending=[True, False])
            
            if not f2_visible.empty:
                sum_row = pd.DataFrame({'Ilce': ['TOPLAM'], 'Urun': ['-'], 'Tuketim': [f2_visible['Tuketim'].sum()], 'Stok': [f2_visible['Stok'].sum()], 'Ihtiyac': [f2_visible['Ihtiyac'].sum()], 'Gonderilecek': [f2_visible['Gonderilecek'].sum()]})
                f2_display = pd.concat([f2_visible, sum_row], ignore_index=True)
            else: f2_display = f2_visible

            st.subheader("İlçe Bazlı Toplam İhtiyaçlar")
            st.dataframe(f2_display, use_container_width=True)
            c5, c6 = st.columns(2)
            with c5: st.download_button("📥 İlçe Excel", to_excel(f2_display), "ilce_ozet.xlsx")
            with c6: st.download_button("📥 İlçe PDF", to_pdf(f2_display, "Ilce Ozet"), "ilce_ozet.pdf")
        
        with tab4:
            st.subheader("📊 İl Geneli Toplam Stok ve Tüketim Analizi")
            grp_tuketim_saha = df_t_saha.groupby('ÜRÜN TANIMI')['Tuketim'].sum()
            grp_stok_saha = df_s_saha.groupby('ÜRÜN TANIMI')['Stok'].sum()
            grp_stok_ism = df_s_ism.groupby('ÜRÜN TANIMI')['Stok'].sum()
            grp_tuketim_ism = df_t_ism.groupby('ÜRÜN TANIMI')['Tuketim'].sum() 
            grp_tuketim_total = grp_tuketim_saha.add(grp_tuketim_ism, fill_value=0)
            
            all_vaccines = grp_stok_saha.index.union(grp_stok_ism.index).union(grp_tuketim_total.index)
            df_genel = pd.DataFrame(index=all_vaccines)
            df_genel.index.name = 'Urun'
            df_genel['İl Ana Depo (ISM)'] = grp_stok_ism
            df_genel['Saha (TSM, ASM, Son)'] = grp_stok_saha
            df_genel['Toplam Tüketim'] = grp_tuketim_total
            df_genel = df_genel.fillna(0)
            df_genel['İl Geneli Stok'] = df_genel['İl Ana Depo (ISM)'] + df_genel['Saha (TSM, ASM, Son)']
            df_genel['Günlük ortalama tüketim'] = (df_genel['Toplam Tüketim'] / oto_gun_sayisi).round(2)
            df_genel['Yetme Süresi (Gün)'] = df_genel.apply(lambda r: round(r['İl Geneli Stok'] / r['Günlük ortalama tüketim'], 1) if r['Günlük ortalama tüketim'] > 0 else 999, axis=1)
            df_genel['İl Ana Depo Yetme Süresi (Gün)'] = df_genel.apply(lambda r: round(r['İl Ana Depo (ISM)'] / r['Günlük ortalama tüketim'], 1) if r['Günlük ortalama tüketim'] > 0 else 999, axis=1)

            df_genel = df_genel.reset_index()
            cols_order = ['Urun', 'İl Geneli Stok', 'İl Ana Depo (ISM)', 'İl Ana Depo Yetme Süresi (Gün)', 'Saha (TSM, ASM, Son)', 'Toplam Tüketim', 'Günlük ortalama tüketim', 'Yetme Süresi (Gün)']
            if 'Urun' not in df_genel.columns: df_genel.rename(columns={df_genel.columns[0]: 'Urun'}, inplace=True)
            df_genel = df_genel[cols_order]

            st.markdown("### ⏳ Aşı Bazlı Yetme Süresi Analizi")
            chart_df = df_genel.copy()
            chart_df['Visual_Value'] = chart_df['Yetme Süresi (Gün)'].apply(lambda x: 180 if x > 180 else x)
            chart_df['Label'] = chart_df['Yetme Süresi (Gün)'].apply(lambda x: "180+" if x > 180 else f"{x:.1f}")
            chart_df['Color'] = chart_df['Yetme Süresi (Gün)'].apply(lambda val: '#ff4b4b' if val < 15 else '#ffa500' if val < 30 else '#ffe066' if val < 60 else '#90ee90')
            
            base = alt.Chart(chart_df).encode(x=alt.X('Urun', sort='-y', title='Aşılar'), tooltip=['Urun', 'Yetme Süresi (Gün)', 'İl Geneli Stok', 'Günlük ortalama tüketim'])
            bars = base.mark_bar().encode(y=alt.Y('Visual_Value', title='Yetme Süresi (Gün) [Maks 180]'), color=alt.Color('Color', scale=None, legend=None))
            text = base.mark_text(align='center', baseline='bottom', dy=-5).encode(y='Visual_Value', text='Label')
            st.altair_chart((bars + text).properties(height=400).interactive(), use_container_width=True)

            def highlight_yetme_suresi(val):
                if not isinstance(val, (int, float)): return ''
                if val < 15: return 'background-color: #ff4b4b; color: white'
                elif val < 30: return 'background-color: #ffa500; color: black'
                elif val < 60: return 'background-color: #ffe066; color: black'
                else: return 'background-color: #90ee90; color: black'

            styled_df = df_genel.style.map(highlight_yetme_suresi, subset=['Yetme Süresi (Gün)', 'İl Ana Depo Yetme Süresi (Gün)'])
            styled_df = styled_df.format({"Günlük ortalama tüketim": "{:.2f}", "Yetme Süresi (Gün)": "{:.1f}", "İl Ana Depo Yetme Süresi (Gün)": "{:.1f}", "İl Geneli Stok": "{:.0f}", "İl Ana Depo (ISM)": "{:.0f}", "Saha (TSM, ASM, Son)": "{:.0f}", "Toplam Tüketim": "{:.0f}"})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            c7, c8 = st.columns(2)
            with c7: st.download_button("📥 İl Geneli Excel", to_excel(df_genel), "il_geneli_ozet.xlsx")
            with c8: st.download_button("📥 İl Geneli PDF", to_pdf(df_genel, "Il Geneli Stok ve Tuketim"), "il_geneli_ozet.pdf")

        with tab5:
            st.subheader("📉 Zayi ve Verimlilik Analizi")
            analiz_turu = st.radio("Analiz Türü Seçin:", ("Tüm Aşılar (Genel Görünüm)", "Sadece Tekli Doz Aşılar (Kritik Analiz)"), horizontal=True)
            st.info("💡 Not: 'Sadece Tekli Doz' seçeneği; BCG, Oral Polio ve PPD gibi çoklu dozlu aşıları hariç tutarak, operasyonel zayiyi (kırılma, soğuk zincir vb.) gösterir.")
            
            df_zayi = df_f.copy()
            if analiz_turu == "Sadece Tekli Doz Aşılar (Kritik Analiz)": df_zayi = df_zayi[~df_zayi['Urun'].str.upper().str.contains('BCG|POLIO|PPD', regex=True)]

            zayi_ozet = df_zayi.groupby('Ilce').agg({'Tuketim': 'sum', 'Zayi': 'sum'}).reset_index()
            zayi_ozet['Zayi Oranı (%)'] = zayi_ozet.apply(lambda x: (x['Zayi'] / (x['Tuketim'] + x['Zayi']) * 100) if (x['Tuketim'] + x['Zayi']) > 0 else 0, axis=1).round(2)
            zayi_ozet = zayi_ozet.sort_values('Zayi', ascending=False)
            
            col_z1, col_z2 = st.columns(2)
            with col_z1:
                st.markdown("#### 🏙️ İlçelere Göre Zayi Durumu")
                st.dataframe(zayi_ozet, use_container_width=True, hide_index=True)
            with col_z2:
                st.markdown("#### 💉 Aşılara Göre Toplam Zayi")
                asi_zayi = df_zayi.groupby('Urun')['Zayi'].sum().reset_index().sort_values('Zayi', ascending=False)
                st.dataframe(asi_zayi, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown(f"#### 🏢 En Çok Zayi Veren 20 Kurum ({analiz_turu})")
            kurum_zayi = df_zayi.groupby(['Ilce', 'Birim', 'Urun']).agg({'Zayi': 'sum'}).reset_index()
            kurum_zayi = kurum_zayi[kurum_zayi['Zayi'] > 0].sort_values('Zayi', ascending=False).head(20)
            st.dataframe(kurum_zayi, use_container_width=True, hide_index=True)
            
            c9, c10 = st.columns(2)
            with c9: st.download_button("📥 Zayi Analizi Excel", to_excel(zayi_ozet), "zayi_analizi.xlsx")
            with c10: st.download_button("📥 Zayi Analizi PDF", to_pdf(zayi_ozet, "Zayi Analizi"), "zayi_analizi.pdf")
            
            st.markdown("---")
            st.markdown("### 📥 Detaylı Zayi Raporu (İlçe + Aşı Bazlı)")
            zayi_detay = df_zayi.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Zayi': 'sum'}).reset_index()
            zayi_detay['Zayi Oranı (%)'] = zayi_detay.apply(lambda x: (x['Zayi'] / (x['Tuketim'] + x['Zayi']) * 100) if (x['Tuketim'] + x['Zayi']) > 0 else 0, axis=1).round(2)
            zayi_detay = zayi_detay.sort_values(['Ilce', 'Zayi'], ascending=[True, False])
            st.download_button("📥 Detaylı Zayi Raporu İndir (İlçe + Aşı)", to_excel(zayi_detay), "detayli_zayi_analizi.xlsx")

        with tab6:
            st.subheader("🔄 Akıllı Transfer Önerileri (İlçe İçi)")
            
            # --- YENİ EKLENEN ÖNCELİK SEÇİMİ ---
            transfer_oncelik = st.radio(
                "Transfer Hedefi Önceliği Seçiniz:",
                ["Tümü (Genel)", "Sadece ASM'ler (Aile Sağlığı Merkezleri)", "Sadece Son Kullanıcı Birimleri"],
                horizontal=True
            )
            
            st.markdown("""
            Bu modül, aynı ilçe içinde **fazla stoğu olan** birimlerle **aşı ihtiyacı olan** birimleri eşleştirir.
            * **En az 10 doz** transfer edilecekse öneri oluşturulur.
            * İl Depoları (İSM), TSM ve diğer depolar bu hesaplamaya **dahil edilmez**.
            """)
            
            transfer_onerileri = []
            
            for ilce in df_f['Ilce'].unique():
                df_ilce = df_f[df_f['Ilce'] == ilce]
                
                # Depoları tamamen çıkar (hem alıcı hem verici olamazlar)
                df_ilce_transfer = df_ilce[~df_ilce['Tip'].astype(str).str.upper().apply(lambda x: any(k in x for k in ['ISM', 'TSM', 'DEPO']))].copy()
                
                for urun in df_ilce_transfer['Urun'].unique():
                    # Potansiyel Alıcılar (İhtiyacı olanlar)
                    alicilar = df_ilce_transfer[(df_ilce_transfer['Urun'] == urun) & (df_ilce_transfer['Gonderilecek'] > 0)].copy()
                    
                    # --- ÖNCELİK FİLTRESİ UYGULAMA ---
                    if transfer_oncelik == "Sadece ASM'ler (Aile Sağlığı Merkezleri)":
                        alicilar = alicilar[alicilar['Tip'].astype(str).str.upper().str.contains("ASM")]
                    elif transfer_oncelik == "Sadece Son Kullanıcı Birimleri":
                        alicilar = alicilar[alicilar['Tip'].astype(str).str.upper().str.contains("SON KULLANICI")]
                    
                    # Potansiyel Vericiler (Fazlası olanlar)
                    vericiler = df_ilce_transfer[(df_ilce_transfer['Urun'] == urun) & (df_ilce_transfer['Fazla_Miktar'] > 0)].copy()
                    
                    if alicilar.empty or vericiler.empty:
                        continue
                        
                    vericiler = vericiler.sort_values('Fazla_Miktar', ascending=False)
                    alicilar = alicilar.sort_values('Gonderilecek', ascending=False)
                    
                    for _, verici in vericiler.iterrows():
                        if verici['Fazla_Miktar'] <= 0: continue
                        
                        for idx_alici, alici in alicilar.iterrows():
                            if alici['Gonderilecek'] <= 0: continue
                            
                            transfer_miktar = min(verici['Fazla_Miktar'], alici['Gonderilecek'])
                            
                            if transfer_miktar >= 10:
                                transfer_onerileri.append({
                                    'İlçe': ilce,
                                    'Ürün': urun,
                                    'Kimden (Verici)': verici['Birim'],
                                    'Tip (Verici)': verici['Tip'],
                                    'Kime (Alıcı)': alici['Birim'],
                                    'Tip (Alıcı)': alici['Tip'],
                                    'Transfer Miktarı': int(transfer_miktar),
                                    'Verici Kalan Fazla': int(verici['Fazla_Miktar'] - transfer_miktar),
                                    'Alıcı Kalan İhtiyaç': int(alici['Gonderilecek'] - transfer_miktar)
                                })
                                
                                verici['Fazla_Miktar'] -= transfer_miktar
                                alicilar.at[idx_alici, 'Gonderilecek'] -= transfer_miktar

            if transfer_onerileri:
                df_transfer = pd.DataFrame(transfer_onerileri)
                st.success(f"Toplam {len(df_transfer)} adet (10 Doz+) transfer önerisi bulundu. ({transfer_oncelik})")
                st.dataframe(df_transfer, use_container_width=True)
                
                c_tr1, c_tr2 = st.columns(2)
                with c_tr1: st.download_button("📥 Transfer Önerileri Excel", to_excel(df_transfer), "akilli_transfer.xlsx")
                with c_tr2: st.download_button("📥 Transfer Önerileri PDF", to_pdf(df_transfer, "Akilli Transfer Onerileri"), "akilli_transfer.pdf")
            else:
                st.info(f"Seçilen kriterlere göre ({transfer_oncelik}, En az 10 doz) transfer fırsatı bulunamadı.")

    except Exception as e:
        st.error(f"Hata: {e}")
else:
    st.info("Lütfen dosyaları yükleyin.")
