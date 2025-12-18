import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

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
    """CSV dosyasının ilk satırlarından tarihleri otomatik çıkarır."""
    start_date = None
    end_date = None
    
    # Dosyanın başına dön ve ilk 15 satırı oku
    file.seek(0)
    lines = [file.readline().decode('iso-8859-9') for _ in range(15)]
    file.seek(0) # Dosyayı tekrar başa sar ki pandas okuyabilsin

    for line in lines:
        if "Baslangiç Tarihi" in line:
            parts = line.split(',')
            for p in parts:
                if "20" in p and "." in p: # Tarih formatı kontrolü
                    start_date = p.strip().replace('"', '')
        if "Bitis Tarihi" in line:
            parts = line.split(',')
            for p in parts:
                if "20" in p and "." in p:
                    end_date = p.strip().replace('"', '')
    
    if start_date and end_date:
        try:
            d1 = datetime.strptime(start_date, "%d.%m.%Y")
            d2 = datetime.strptime(end_date, "%d.%m.%Y")
            diff = (d2 - d1).days + 1
            return diff, start_date, end_date
        except:
            return 91, None, None
    return 91, None, None

def process_data(t_df, s_df, gun_sayisi):
    try:
        t_df.columns = [c.strip() for c in t_df.columns]
        s_df.columns = [c.strip() for c in s_df.columns]
        
        t_df[['ILÇE', 'BIRIM']] = t_df[['ILÇE', 'BIRIM']].ffill()
        s_df[['ILÇE', 'BIRIM ADI']] = s_df[['ILÇE', 'BIRIM ADI']].ffill()
        
        t_df['Tuketim'] = pd.to_numeric(t_df['UYGULANAN DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0)
        s_df['Stok'] = pd.to_numeric(s_df['TOPLAM DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0)

        df_c = t_df.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI'])['Tuketim'].sum().reset_index()
        df_c.columns = ['Ilce', 'Birim', 'Urun', 'Tuketim']
        
        df_s = s_df.groupby(['ILÇE', 'BIRIM ADI', 'ÜRÜN TANIMI'])['Stok'].sum().reset_index()
        df_s.columns = ['Ilce', 'Birim', 'Urun', 'Stok']
        
        merged = pd.merge(df_c, df_s, on=['Ilce', 'Birim', 'Urun'], how='outer').fillna(0)
        
        # Otomatik Gelen Gün Sayısı Kullanılıyor
        merged['Ihtiyac'] = (((merged['Tuketim'] / gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - merged['Stok']
        merged['Gonderilecek'] = merged['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
        
        return merged
    except Exception as e:
        st.error(f"Hata: {e}")
        return None

# --- DOSYA YÜKLEME ---
col1, col2 = st.columns(2)
with col1:
    tuketim_file = st.file_uploader("📂 1. Dönemsel Tüketim Raporu (CSV)", type=["csv"])
with col2:
    stok_file = st.file_uploader("📂 2. İl Genel Stok Raporu (CSV)", type=["csv"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file:
    # 1. TARİHLERİ OTOMATİK ÇIKAR
    oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_csv(tuketim_file)
    
    # Bilgi Paneli
    if s_tarih:
        st.sidebar.info(f"📅 **Rapor Süresi:** {s_tarih} - {b_tarih} ({oto_gun_sayisi} Gün)")
    else:
        st.sidebar.warning("⚠️ Tarihler otomatik okunamadı, varsayılan (91 gün) kullanılıyor.")

    # 2. VERİLERİ OKU VE İŞLE
    df_raw_t = pd.read_csv(tuketim_file, header=7, encoding='iso-8859-9')
    df_raw_s = pd.read_csv(stok_file, header=3, encoding='iso-8859-9')
    
    res_df = process_data(df_raw_t, df_raw_s, oto_gun_sayisi)
    
    if res_df is not None:
        # FİLTRELER
        st.sidebar.markdown("---")
        secilen_ilceler = st.sidebar.multiselect("İlçe Seçin", sorted(res_df['Ilce'].unique()))
        secilen_asilar = st.sidebar.multiselect("Aşı Türü Seçin", sorted(res_df['Urun'].unique()))

        tab1, tab2 = st.tabs(["🏢 Kurum Bazlı Plan", "📍 İlçe Bazlı Plan"])

        # --- SEKME 1 ---
        with tab1:
            df1 = res_df.copy()
            if secilen_ilceler: df1 = df1[df1['Ilce'].isin(secilen_ilceler)]
            if secilen_asilar: df1 = df1[df1['Urun'].isin(secilen_asilar)]
            
            final1 = df1[df1['Gonderilecek'] > 0].sort_values('Gonderilecek', ascending=False)
            st.dataframe(final1[['Ilce', 'Birim', 'Urun', 'Tuketim', 'Stok', 'Gonderilecek']], use_container_width=True)
            st.download_button("📥 Kurum Listesini İndir", final1.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "kurum.csv", "text/csv")

        # --- SEKME 2 ---
        with tab2:
            df2 = res_df.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            if secilen_ilceler: df2 = df2[df2['Ilce'].isin(secilen_ilceler)]
            if secilen_asilar: df2 = df2[df2['Urun'].isin(secilen_asilar)]
            
            df2['Ihtiyac'] = (((df2['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df2['Stok']
            df2['Gonderilecek'] = df2['Ihtiyac'].apply(lambda x: np.ceil(x) if x > 0 else 0)
            
            final2 = df2[df2['Gonderilecek'] > 0].sort_values(['Ilce', 'Gonderilecek'], ascending=[True, False])
            st.dataframe(final2, use_container_width=True)
            st.download_button("📥 İlçe Listesini İndir", final2.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "ilce.csv", "text/csv")
else:
    st.info("Lütfen dosyaları yükleyin.")