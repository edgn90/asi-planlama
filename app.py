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

# --- DOSYA YÜKLEME ALANI (GÜNCELLENDİ) ---
col_u1, col_u2 = st.columns(2)
with col_u1:
    tuketim_file = st.file_uploader("📂 Dönemsel Tüketim Raporu (CSV)", type=["csv"])
with col_u2:
    stok_file = st.file_uploader("📂 Stok Durum Raporu Birim Bazında (CSV)", type=["csv"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file:
    try:
        oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_csv(tuketim_file)
        
        # --- CSV OKUMA VE HATA YÖNETİMİ ---
        # 1. Tüketim Dosyası
        try:
            tuketim_file.seek(0)
            df_raw_t = pd.read_csv(tuketim_file, header=7, encoding='utf-8')
        except Exception:
            tuketim_file.seek(0)
            df_raw_t = pd.read_csv(tuketim_file, header=7, encoding='iso-8859-9')
            
        # 2. Stok Dosyası
        try:
            stok_file.seek(0)
            df_raw_s = pd.read_csv(stok_file, header=3, encoding='utf-8')
        except Exception:
            stok_file.seek(0)
            df_raw_s = pd.read_csv(stok_file, header=3, encoding='iso-8859-9')
        
        # Sütun isimlerini temizle
        df_raw_t.columns = [c.strip() for c in df_raw_t.columns]
        df_raw_s.columns = [c.strip() for c in df_raw_s.columns]

        # --- AKILLI SÜTUN ONARICI ---
        def smart_fix_columns(df):
            rename_map = {}
            for col in df.columns:
                col_upper = col.upper()
                if col_upper.startswith('IL') and col_upper.endswith('E'): 
                    rename_map[col] = 'ILÇE'
                elif 'BIRIM' in col_upper and 'ADI' in col_upper:
                    rename_map[col] = 'BIRIM ADI'
                elif 'BIRIM' in col_upper and 'TIPI' in col_upper:
                    rename_map[col] = 'BIRIM TIPI'
                elif 'TAN' in col_upper and 'IMI' in col_upper:
                    rename_map[col] = 'ÜRÜN TANIMI'
                elif 'TOPLAM' in col_upper and 'DOZ' in col_upper:
                    rename_map[col] = 'TOPLAM DOZ'
            
            if rename_map:
                df.rename(columns=rename_map, inplace=True)
            return df

        df_raw_s = smart_fix_columns(df_raw_s)
        df_raw_t = smart_fix_columns(df_raw_t)

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
        
        df_s = df_stok_hesaplama.groupby(['ILÇE', 'BIRIM ADI', 'BIRIM TIPI', 'ÜRÜN TANIMI'])['Stok'].sum().reset_index()
        df_s.columns = ['Ilce', 'Birim', 'Tip', 'Urun', 'Stok']
        
        res_df = pd.merge(df_c, df_s, on=['Ilce', 'Birim', 'Urun'], how='outer').fillna(0)
        
        # Hesaplama
        res_df['Gunluk_Hiz'] = res_df['Tuketim'] / oto_gun_sayisi
        res_df['Ihtiyac'] = ((res_df['Gunluk_Hiz'] * plan_suresi) * (1 + guvenlik_marji)) - res_df['Stok']
        res_df['Gonderilecek'] = res_df['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
        res_df['Yetme_Suresi'] = res_df.apply(lambda r: round(r['Stok'] / r['Gunluk_Hiz'], 1) if r['Gunluk_Hiz'] > 0 else 999, axis=1)

        # Durum Belirleme
        def get_durum(row):
            if row['Yetme_Suresi'] < kritik_esik:
                return "🚨 KRİTİK"
            tip_str = str(row['Tip']).upper()
            if row['Yetme_Suresi'] > asiri_esik:
                if any(x in tip_str for x in ['ASM', 'SON KULLANICI']):
                    return "⚠️ AŞIRI"
            return "✅ Yeterli"

        res_df['Durum'] = res_df.apply(get_durum, axis=1)

        # --- YAN MENÜ: FİLTRELER ---
        sec_ilce = st.sidebar.multiselect("📍 İlçe Filtrele", options=sorted(res_df['Ilce'].unique()))
        sec_asi = st.sidebar.multiselect("💉 Aşı Filtrele", options=sorted(res_df['Urun'].unique()))
        
        with st.sidebar.expander("🚚 ANA DEPO (İSM)", expanded=False):
            if not df_ana_depo_stok.empty:
                st.dataframe(df_ana_depo_stok[['ÜRÜN TANIMI', 'Stok']], hide_index=True)
            else:
                st.write("Veri yok.")

        # --- FİLTRE UYGULAMA ---
        df_f = res_df.copy()
        if sec_ilce: df_f = df_f[df_f['Ilce'].isin(sec_ilce)]
        if sec_asi: df_f = df_f[df_f['Urun'].isin(sec_asi)]

        # --- ANA EKRAN GÖRÜNÜMÜ ---
        st.markdown("---")
        if s_tarih:
            st.info(f"📅 **Dönemsel Tüketim Raporu:** {s_tarih} - {b_tarih} ({oto_gun_sayisi} Gün)")

        # Metrikler
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

        # 3 SEKMELİ YAPI
        tab1, tab2, tab3 = st.tabs(["📦 Sevkiyat Planı", "⚠️ Fazla Stok Yönetimi", "📍 İlçe Bazlı Özet"])

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
            st.caption(f"Aşağıdaki liste, {asiri_esik} günden fazla stoğu bulunan ve 'Aşırı' olarak işaretlenen kurumları içerir.")
            f1_asiri = df_f[df_f['Durum'] == "⚠️ AŞIRI"].copy().sort_values('Yetme_Suresi', ascending=False)
            st.dataframe(f1_asiri[['Ilce', 'Birim', 'Urun', 'Stok', 'Yetme_Suresi']], use_container_width=True)
            c3, c4 = st.columns(2)
            with c3: st.download_button("📥 İade Excel", to_excel(f1_asiri), "asiri_stok.xlsx")
            with c4: st.download_button("📥 İade PDF", to_pdf(f1_asiri, "Asiri Stok"), "asiri_stok.pdf")

        with tab3:
            df_i = df_f.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            df_i['Ihtiyac'] = (((df_i['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df_i['Stok']
            df_i['Gonderilecek'] = df_i['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
            f2_visible = df_i[df_i['Gonderilecek'] > 0].copy().sort_values(['Ilce', 'Gonderilecek'], ascending=[True, False])
            
            st.subheader("İlçe Bazlı Toplam İhtiyaçlar")
            st.dataframe(f2_visible, use_container_width=True)
            c5, c6 = st.columns(2)
            with c5: st.download_button("📥 İlçe Excel", to_excel(f2_visible), "ilce_ozet.xlsx")
            with c6: st.download_button("📥 İlçe PDF", to_pdf(f2_visible, "Ilce Ozet"), "ilce_ozet.pdf")

    except Exception as e:
        st.error(f"Hata: {e}")
else:
    st.info("Lütfen dosyaları yükleyin.")
