import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from fpdf import FPDF

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

def tr_fix(text):
    """PDF için Türkçe karakterleri ve emojileri temizler."""
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("🚨", "").replace("✅", "")
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
    # Kolon genişliği hesaplama (Daha esnek bir görünüm için)
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

# --- YAN MENÜ (AYARLAR) ---
st.sidebar.header("⚙️ Planlama Parametreleri")
plan_suresi = st.sidebar.slider("Planlanacak Süre (Gün)", 7, 90, 15)
guvenlik_marji = st.sidebar.slider("Güvenlik Stoğu (%)", 0, 100, 20) / 100
kritik_esik = st.sidebar.number_input("Kritik Stok Eşiği (Gün)", value=3)

# --- DOSYA YÜKLEME ALANI ---
col_u1, col_u2 = st.columns(2)
with col_u1:
    tuketim_file = st.file_uploader("📂 1. Dönemsel Tüketim Raporu (CSV)", type=["csv"])
with col_u2:
    stok_file = st.file_uploader("📂 2. İl Genel Stok Raporu (CSV)", type=["csv"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file:
    try:
        oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_csv(tuketim_file)
        
        df_raw_t = pd.read_csv(tuketim_file, header=7, encoding='iso-8859-9')
        df_raw_s = pd.read_csv(stok_file, header=3, encoding='iso-8859-9')
        
        df_raw_t.columns = [c.strip() for c in df_raw_t.columns]
        df_raw_s.columns = [c.strip() for c in df_raw_s.columns]
        df_raw_t[['ILÇE', 'BIRIM']] = df_raw_t[['ILÇE', 'BIRIM']].ffill()
        df_raw_s[['ILÇE', 'BIRIM ADI', 'BIRIM TIPI']] = df_raw_s[['ILÇE', 'BIRIM ADI', 'BIRIM TIPI']].ffill()
        
        df_raw_t['Tuketim'] = pd.to_numeric(df_raw_t['UYGULANAN DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0)
        stok_col = 'TOPLAM DOZ' if 'TOPLAM DOZ' in df_raw_s.columns else df_raw_s.columns[-1]
        df_raw_s['Stok'] = pd.to_numeric(df_raw_s[stok_col].astype(str).apply(clean_number), errors='coerce').fillna(0)

        # --- ANA DEPO AYRIŞTIRMA ---
        is_ana_depo = (df_raw_s['ILÇE'].str.contains('FATIH', case=False, na=False)) & \
                      (df_raw_s['BIRIM ADI'].str.contains('ISTANBUL ISM', case=False, na=False)) & \
                      (df_raw_s['BIRIM TIPI'].str.contains('ISM', case=False, na=False))
        
        df_ana_depo_stok = df_raw_s[is_ana_depo].copy()
        df_stok_hesaplama = df_raw_s[~is_ana_depo].copy()
        
        df_c = df_raw_t.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI'])['Tuketim'].sum().reset_index()
        df_c.columns = ['Ilce', 'Birim', 'Urun', 'Tuketim']
        df_s = df_stok_hesaplama.groupby(['ILÇE', 'BIRIM ADI', 'ÜRÜN TANIMI'])['Stok'].sum().reset_index()
        df_s.columns = ['Ilce', 'Birim', 'Urun', 'Stok']
        
        res_df = pd.merge(df_c, df_s, on=['Ilce', 'Birim', 'Urun'], how='outer').fillna(0)
        
        # Hesaplama
        res_df['Gunluk_Hiz'] = res_df['Tuketim'] / oto_gun_sayisi
        res_df['Ihtiyac'] = ((res_df['Gunluk_Hiz'] * plan_suresi) * (1 + guvenlik_marji)) - res_df['Stok']
        res_df['Gonderilecek'] = res_df['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
        
        res_df['Yetme_Suresi'] = res_df.apply(lambda r: round(r['Stok'] / r['Gunluk_Hiz'], 1) if r['Gunluk_Hiz'] > 0 else 999, axis=1)
        res_df['Durum'] = res_df['Yetme_Suresi'].apply(lambda x: "🚨 KRİTİK" if x < kritik_esik else "✅ Yeterli")

        # --- YAN MENÜ: FİLTRELER VE DEPO ---
        st.sidebar.markdown("---")
        sec_ilce = st.sidebar.multiselect("📍 İlçe Seçin", options=sorted(res_df['Ilce'].unique()))
        sec_asi = st.sidebar.multiselect("💉 Aşı Türü Seçin", options=sorted(res_df['Urun'].unique()))
        
        st.sidebar.markdown("---")
        with st.sidebar.expander("🚚 İL ANA DEPO STOKLARI", expanded=False):
            st.dataframe(df_ana_depo_stok[['ÜRÜN TANIMI', 'Stok']], hide_index=True)

        # --- ANA EKRAN ---
        df_f = res_df.copy()
        if sec_ilce: df_f = df_f[df_f['Ilce'].isin(sec_ilce)]
        if sec_asi: df_f = df_f[df_f['Urun'].isin(sec_asi)]

        st.markdown("---")
        if s_tarih:
            st.info(f"📅 **Rapor Dönemi:** {s_tarih} - {b_tarih} ({oto_gun_sayisi} Gün)")

        # Metrikler
        toplam_sevk = int(df_f['Gonderilecek'].sum())
        kritik_sayisi = len(df_f[df_f['Durum'] == "🚨 KRİTİK"])
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 TOPLAM SEVKİYAT (DOZ)", f"{toplam_sevk:,}".replace(",", "."))
        m2.metric("🚨 KRİTİK STOK SAYISI", kritik_sayisi)
        m3.metric("🏢 KURUM SAYISI", df_f[df_f['Gonderilecek'] > 0]['Birim'].nunique())

        if kritik_sayisi > 0:
            st.error(f"⚠️ **Kritik Eşik Uyarısı:** Stoğu {kritik_esik} günden az kalan {kritik_sayisi} birim tespit edildi.")

        st.markdown("---")

        tab1, tab2 = st.tabs(["🏢 Kurum Bazlı Plan", "📍 İlçe Bazlı Özet"])

        with tab1:
            f1 = df_f[df_f['Gonderilecek'] > 0].sort_values(['Durum', 'Gonderilecek'], ascending=[False, False])
            st.dataframe(f1[['Durum', 'Ilce', 'Birim', 'Urun', 'Tuketim', 'Stok', 'Gonderilecek']], use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📥 Excel İndir", to_excel(f1), "kurum_bazli_plan.xlsx")
            with c2:
                st.download_button("📥 PDF İndir", to_pdf(f1, "Kurum Bazli Dagitim Plani"), "kurum_bazli_plan.pdf")

        with tab2:
            df_i = df_f.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            df_i['Ihtiyac'] = (((df_i['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df_i['Stok']
            df_i['Gonderilecek'] = df_i['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
            f2 = df_i[df_i['Gonderilecek'] > 0].sort_values('Gonderilecek', ascending=False)
            
            st.subheader("İlçe Bazlı Toplam İhtiyaçlar")
            st.dataframe(f2, use_container_width=True)
            
            # İHTİYAÇ DUYDUĞUNUZ EKLEME: İLÇE BAZLI İNDİRME BUTONLARI
            c3, c4 = st.columns(2)
            with c3:
                st.download_button("📥 Excel (İlçe) İndir", to_excel(f2), "ilce_bazli_ozet.xlsx")
            with c4:
                st.download_button("📥 PDF (İlçe) İndir", to_pdf(f2, "Ilce Bazli Toplam Asi Ihtiyaci"), "ilce_bazli_ozet.pdf")

    except Exception as e:
        st.error(f"Hata: {e}")
else:
    st.info("Lütfen dosyaları yükleyin.")
