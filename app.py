import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from fpdf import FPDF

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Akıllı Aşı Lojistik Paneli", layout="wide")

st.title("💉 Akıllı Aşı Talep Tahmini ve Stok Yönetim Paneli")

# --- YAN MENÜ (AYARLAR) ---
st.sidebar.header("⚙️ Planlama Parametreleri")
plan_suresi = st.sidebar.slider("Planlanacak Süre (Gün)", 7, 90, 15)
guvenlik_marji = st.sidebar.slider("Güvenlik Stoğu (%)", 0, 100, 20) / 100

# --- YARDIMCI FONKSİYONLAR ---
def clean_number(x):
    if isinstance(x, str):
        return x.replace('.', '').replace(',', '').replace('"', '').strip()
    return x

def get_dates_from_csv(file):
    try:
        file.seek(0)
        lines = [file.readline().decode('iso-8859-9') for _ in range(15)]
        file.seek(0)
        start_date, end_date = None, None
        for line in lines:
            if "Baslangiç Tarihi" in line:
                parts = line.split(',')
                for p in parts:
                    if "20" in p and "." in p: start_date = p.strip().replace('"', '')
            if "Bitis Tarihi" in line:
                parts = line.split(',')
                for p in parts:
                    if "20" in p and "." in p: end_date = p.strip().replace('"', '')
        if start_date and end_date:
            d1 = datetime.strptime(start_date, "%d.%m.%Y")
            d2 = datetime.strptime(end_date, "%d.%m.%Y")
            diff = (d2 - d1).days + 1
            return diff, start_date, end_date
    except:
        pass
    return 91, None, None

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Plan')
    return output.getvalue()

def to_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, title, ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", "B", 8)
    cols = df.columns.tolist()
    for col in cols:
        pdf.cell(32, 8, str(col), 1)
    pdf.ln()
    pdf.set_font("Arial", "", 7)
    for i in range(len(df)):
        for col in cols:
            val = str(df.iloc[i][col])
            pdf.cell(32, 7, val[:22], 1)
        pdf.ln()
    return pdf.output()

# --- DOSYA YÜKLEME ALANI (HER ZAMAN GÖRÜNÜR) ---
col_u1, col_u2 = st.columns(2)
with col_u1:
    tuketim_file = st.file_uploader("📂 1. Dönemsel Tüketim Raporu (CSV)", type=["csv"])
with col_u2:
    stok_file = st.file_uploader("📂 2. İl Genel Stok Raporu (CSV)", type=["csv"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file:
    try:
        # Tarih ve Gün Sayısı
        oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_csv(tuketim_file)
        if s_tarih:
            st.sidebar.info(f"📅 Rapor Dönemi: {s_tarih} - {b_tarih}\n({oto_gun_sayisi} Gün üzerinden hesaplanıyor)")

        # Dosyaları Oku
        df_raw_t = pd.read_csv(tuketim_file, header=7, encoding='iso-8859-9')
        df_raw_s = pd.read_csv(stok_file, header=3, encoding='iso-8859-9')
        
        # Temizlik ve Hazırlık
        df_raw_t.columns = [c.strip() for c in df_raw_t.columns]
        df_raw_s.columns = [c.strip() for c in df_raw_s.columns]
        df_raw_t[['ILÇE', 'BIRIM']] = df_raw_t[['ILÇE', 'BIRIM']].ffill()
        df_raw_s[['ILÇE', 'BIRIM ADI']] = df_raw_s[['ILÇE', 'BIRIM ADI']].ffill()
        
        df_raw_t['Tuketim'] = pd.to_numeric(df_raw_t['UYGULANAN DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0)
        stok_col = 'TOPLAM DOZ' if 'TOPLAM DOZ' in df_raw_s.columns else df_raw_s.columns[-1]
        df_raw_s['Stok'] = pd.to_numeric(df_raw_s[stok_col].astype(str).apply(clean_number), errors='coerce').fillna(0)
        
        # Gruplama ve Birleştirme
        df_c = df_raw_t.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI'])['Tuketim'].sum().reset_index()
        df_s = df_raw_s.groupby(['ILÇE', 'BIRIM ADI', 'ÜRÜN TANIMI'])['Stok'].sum().reset_index()
        res_df = pd.merge(df_c, df_s, left_on=['ILÇE', 'BIRIM', 'ÜRÜN TANIMI'], right_on=['ILÇE', 'BIRIM ADI', 'ÜRÜN TANIMI'], how='outer').fillna(0)
        res_df = res_df[['ILÇE', 'BIRIM', 'ÜRÜN TANIMI', 'Tuketim', 'Stok']]
        res_df.columns = ['Ilce', 'Birim', 'Urun', 'Tuketim', 'Stok']

        # Hesaplama
        res_df['Ihtiyac'] = (((res_df['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - res_df['Stok']
        res_df['Gonderilecek'] = res_df['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)

        # Filtreler
        st.sidebar.markdown("---")
        secilen_ilceler = st.sidebar.multiselect("📍 İlçe Filtrele", options=sorted(res_df['Ilce'].unique()))
        df_filtered = res_df[res_df['Ilce'].isin(secilen_ilceler)] if secilen_ilceler else res_df

        # Sekmeler
        tab1, tab2 = st.tabs(["🏢 Kurum Bazlı Plan", "📍 İlçe Bazlı Özet"])

        with tab1:
            final1 = df_filtered[df_filtered['Gonderilecek'] > 0].sort_values('Gonderilecek', ascending=False)
            st.subheader("Kurum Bazlı Dağıtım Listesi")
            st.dataframe(final1, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📥 Excel Olarak İndir", to_excel(final1), "kurum_plan.xlsx")
            with c2:
                st.download_button("📥 PDF Olarak İndir", to_pdf(final1, "Kurum Plani"), "kurum_plan.pdf")

        with tab2:
            df_ilce = df_filtered.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            df_ilce['Ihtiyac'] = (((df_ilce['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df_ilce['Stok']
            df_ilce['Gonderilecek'] = df_ilce['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
            final2 = df_ilce[df_ilce['Gonderilecek'] > 0].sort_values(['Ilce', 'Gonderilecek'], ascending=[True, False])
            
            st.subheader("İlçe Bazlı Toplam İhtiyaçlar")
            st.dataframe(final2, use_container_width=True)
            
            c3, c4 = st.columns(2)
            with c3:
                st.download_button("📥 Excel (İlçe) İndir", to_excel(final2), "ilce_plan.xlsx")
            with c4:
                st.download_button("📥 PDF (İlçe) İndir", to_pdf(final2, "Ilce Plani"), "ilce_plan.pdf")

    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")
else:
    st.info("Lütfen hesaplama yapmak için her iki CSV dosyasını da yukarıdaki alanlara yükleyin.")
