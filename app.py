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
    if pd.isnull(x): return 0
    if isinstance(x, (int, float)): return x
    return str(x).replace('.', '').replace(',', '').replace('"', '').strip()

def get_dates_from_file(file_obj):
    file_ext = file_obj.name.split('.')[-1].lower()
    start_date, end_date = None, None
    single_date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')
    period_pattern = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})')
    
    lines = []
    if file_ext in ['xlsx', 'xls']:
        try:
            file_obj.seek(0)
            df_temp = pd.read_excel(file_obj, header=None, nrows=15)
            for i in range(len(df_temp)):
                row_vals = [str(x) for x in df_temp.iloc[i].values if pd.notnull(x)]
                lines.append(" ".join(row_vals))
        except: pass
    else:
        file_obj.seek(0)
        try:
            lines = [file_obj.readline().decode('utf-8-sig') for _ in range(15)]
        except:
            file_obj.seek(0)
            lines = [file_obj.readline().decode('iso-8859-9') for _ in range(15)]
            
    for line in lines:
        line_upper = line.upper().replace('İ', 'I')
        if "DÖNEM" in line_upper or "DONEM" in line_upper:
            m = period_pattern.search(line)
            if m:
                start_date, end_date = m.groups()
                break
        if "BASLANGIÇ TARIHI" in line_upper or "BAŞLANGIÇ TARİHİ" in line_upper:
            m = single_date_pattern.search(line)
            if m: start_date = m.group()
        if "BITIS TARIHI" in line_upper or "BİTİŞ TARİHİ" in line_upper:
            m = single_date_pattern.search(line)
            if m: end_date = m.group()

    if start_date and end_date:
        try:
            d1 = datetime.strptime(start_date, "%d.%m.%Y")
            d2 = datetime.strptime(end_date, "%d.%m.%Y")
            return (d2 - d1).days + 1, start_date, end_date
        except: pass
    return 91, None, None

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Rapor')
    return output.getvalue()

def tr_fix(text):
    if not isinstance(text, str): text = str(text)
    text = text.replace("🚨", "").replace("✅", "").replace("⚠️", "")
    rep = {"İ":"I","ı":"i","Ğ":"G","ğ":"g","Ş":"S","ş":"s","ç":"c","Ç":"C","ö":"o","Ö":"O","ü":"u","Ü":"U"}
    for k, v in rep.items(): text = text.replace(k, v)
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
    
    for col in cols: pdf.cell(col_width, 8, tr_fix(str(col)), 1)
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 7)
    for i in range(len(df)):
        for col in cols:
            val = tr_fix(str(df.iloc[i][col]))
            pdf.cell(col_width, 7, val[:25], 1)
        pdf.ln()
    return bytes(pdf.output())

def ozellestirilmis_yuvarlama(val):
    if val <= 0: return 0
    def math_round(n): return int(n + 0.5)
    if val < 100: return math_round(val / 10) * 10
    elif val < 500: return math_round(val / 50) * 50
    else: return math_round(val / 100) * 100

# --- VERİ OKUMA VE SÜTUN STANDARTLAŞTIRMA ---
def standardize_cols(df, source_type):
    rename_map = {}
    for c in df.columns:
        cu = str(c).strip().upper().replace('İ', 'I')
        if source_type == 'master':
            if cu == 'BIRIM' or cu == 'BİRİM' or ('BIRIM' in cu and 'ADI' in cu): rename_map[c] = 'BIRIM'
            elif 'TIP' in cu and 'BIRIM' in cu: rename_map[c] = 'TIP_MASTER'
            elif 'ILÇE' in cu or 'ILCE' in cu: rename_map[c] = 'ILCE_MASTER'
            elif 'UST' in cu and 'BIRIM' in cu: rename_map[c] = 'UST_BIRIM_MASTER'
        elif source_type == 'tuketim':
            if cu == 'BİRİM' or cu == 'BIRIM': rename_map[c] = 'BIRIM'
            elif 'URUN' in cu or 'ÜRÜN' in cu or 'TANIM' in cu: rename_map[c] = 'URUN'
            elif 'UYGULANAN' in cu: rename_map[c] = 'TUKETIM'
            elif 'ZAYI' in cu: rename_map[c] = 'ZAYI'
            elif 'ILÇE' in cu or 'ILCE' in cu: rename_map[c] = 'ILCE_TEMP'
        elif source_type == 'stok':
            if cu == 'BİRİM' or cu == 'BIRIM' or ('BIRIM' in cu and 'ADI' in cu): rename_map[c] = 'BIRIM'
            elif 'URUN' in cu or 'ÜRÜN' in cu or 'TANIM' in cu: rename_map[c] = 'URUN'
            elif 'KALAN' in cu and 'DOZ' in cu: rename_map[c] = 'STOK'
            elif 'TOPLAM' in cu and 'DOZ' in cu and 'STOK' not in rename_map.values(): rename_map[c] = 'STOK'
            elif 'ILÇE' in cu or 'ILCE' in cu: rename_map[c] = 'ILCE_TEMP'
    df.rename(columns=rename_map, inplace=True)
    return df

def load_robust_data(file_obj, source_type):
    ext = file_obj.name.split('.')[-1].lower()
    df = pd.DataFrame()
    
    # AKILLI BAŞLIK DEDEKTÖRÜ: Özet satırlarını atlayıp gerçek tablo başlığını bulur
    def find_header(lines):
        for i, line_raw in enumerate(lines):
            line = str(line_raw).upper().replace('İ', 'I')
            if source_type == 'tuketim':
                if 'BIRIM' in line and 'UYGULANAN' in line: return i
            elif source_type == 'stok':
                if 'BIRIM' in line and ('DOZ' in line or 'QR' in line or 'URUN' in line or 'STOK' in line): return i
            elif source_type == 'master':
                if 'BIRIM' in line and ('ADI' in line or 'TIP' in line or 'ILCE' in line): return i
        return 0

    if ext in ['xlsx', 'xls']:
        try:
            file_obj.seek(0)
            df_temp = pd.read_excel(file_obj, header=None, nrows=25)
            lines = [" ".join([str(x) for x in df_temp.iloc[i].values if pd.notnull(x)]) for i in range(len(df_temp))]
            header_idx = find_header(lines)
            
            file_obj.seek(0)
            df = pd.read_excel(file_obj, header=header_idx)
        except Exception as e:
            if "openpyxl" in str(e).lower():
                st.error("🚨 **Eksik Kütüphane:** Excel okumak için terminalde `pip install openpyxl` çalıştırın.")
                st.stop()
            else:
                st.error(f"Excel hatası: {e}")
                st.stop()
    else:
        file_obj.seek(0)
        lines = []
        for _ in range(25):
            try: lines.append(file_obj.readline().decode('utf-8-sig'))
            except: 
                file_obj.seek(0)
                lines = [line.decode('iso-8859-9', errors='ignore') for line in file_obj.readlines()[:25]]
                break
                
        header_idx = find_header(lines)
        
        methods = [
            {'encoding': 'utf-8', 'sep': ';'},
            {'encoding': 'iso-8859-9', 'sep': ';'},
            {'encoding': 'utf-8', 'sep': ','},
            {'encoding': 'iso-8859-9', 'sep': ','},
            {'encoding': 'iso-8859-9', 'sep': ';', 'quoting': 3, 'on_bad_lines': 'skip'},
            {'encoding': 'utf-8', 'sep': None, 'engine': 'python'}
        ]
        
        for m in methods:
            try:
                file_obj.seek(0)
                kw = {k: v for k, v in m.items() if k != 'encoding'}
                temp_df = pd.read_csv(file_obj, header=header_idx, encoding=m['encoding'], **kw)
                if len(temp_df.columns) > 1:
                    df = temp_df
                    break
            except: continue
            
    if not df.empty:
        df = standardize_cols(df, source_type)
    return df

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Planlama Ayarları")
plan_suresi = st.sidebar.slider("Plan Süresi (Gün)", 1, 60, 10, help="Stokların kaç gün yetecek şekilde planlanacağını seçin.")

st.sidebar.markdown("---")
with st.sidebar.expander("🛠️ Gelişmiş / İnce Ayarlar"):
    guvenlik_marji = st.slider("Güvenlik Payı (%)", 0, 100, 20) / 100
    c1, c2 = st.columns(2)
    with c1: kritik_esik = st.number_input("Kritik (Gün)", value=3)
    with c2: asiri_esik = st.number_input("Aşırı (Gün)", value=60)

# --- DOSYA YÜKLEME ALANI ---
st.markdown("### 📂 Dosya Yükleme")
col_u1, col_u2, col_u3 = st.columns(3)
with col_u1: tuketim_file = st.file_uploader("📂 Tüketim Raporu", type=["csv", "xlsx", "xls"])
with col_u2: stok_file = st.file_uploader("📂 Stok Raporu", type=["csv", "xlsx", "xls"])
with col_u3: birim_file = st.file_uploader("📂 Birimler Listesi (Master)", type=["csv", "xlsx", "xls"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file and birim_file:
    try:
        oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_file(tuketim_file)
        
        # 1. VERİLERİ YÜKLE
        df_b = load_robust_data(birim_file, 'master')
        df_t = load_robust_data(tuketim_file, 'tuketim')
        df_s = load_robust_data(stok_file, 'stok')
        
        if df_b.empty or df_t.empty or df_s.empty:
            st.warning("Dosyalar boş veya beklenen formatta okunamadı.")
            st.stop()

        # Eksik Sütun Kontrolü (Zayi Sütunu Artık İsteğe Bağlı!)
        if 'BIRIM' not in df_b.columns: 
            st.error(f"Master listede 'Birim' sütunu bulunamadı. Lütfen kontrol edin.\n\nBulunan Sütunlar: {list(df_b.columns)}")
            st.stop()
        if 'BIRIM' not in df_t.columns or 'URUN' not in df_t.columns or 'TUKETIM' not in df_t.columns: 
            st.error(f"Tüketim listesinde sütun eksik. (Birim, Ürün veya Uygulanan Doz bulunamadı)\n\nBulunan Sütunlar: {list(df_t.columns)}")
            st.stop()
        if 'BIRIM' not in df_s.columns or 'URUN' not in df_s.columns or 'STOK' not in df_s.columns: 
            st.error(f"Stok listesinde sütun eksik. (Birim, Ürün veya Kalan Doz bulunamadı)\n\nBulunan Sütunlar: {list(df_s.columns)}")
            st.stop()

        # Zayi Sütunu Var mı Kontrolü (Uyarı İçin)
        zayi_var_mi = 'ZAYI' in df_t.columns

        # Master Çoğaltmaları Temizle
        birim_master = df_b.drop_duplicates(subset=['BIRIM']).copy()

        # Tüketim Temizliği (Özet/Toplam Satırlarını at)
        df_t = df_t[~df_t['BIRIM'].astype(str).str.upper().str.contains('TOPLAM', na=False)]
        df_t = df_t[df_t['BIRIM'] != '-']
        if 'ILCE_TEMP' in df_t.columns: df_t = df_t[~df_t['ILCE_TEMP'].astype(str).str.upper().str.contains('TOPLAM', na=False)]

        # Stok Yeni Format için Gruplama (Barkodlu Liste)
        df_s['STOK'] = pd.to_numeric(df_s['STOK'].astype(str).apply(clean_number), errors='coerce').fillna(0)
        df_s = df_s.groupby(['BIRIM', 'URUN'], as_index=False)['STOK'].sum()

        # Sayısal Dönüşümler
        df_t['TUKETIM'] = pd.to_numeric(df_t['TUKETIM'].astype(str).apply(clean_number), errors='coerce').fillna(0)
        df_t['ZAYI'] = pd.to_numeric(df_t['ZAYI'].astype(str).apply(clean_number), errors='coerce').fillna(0) if zayi_var_mi else 0

        # --- MERGE VE SABİTLEME ---
        # Tüketim ve Stok verisini birleştir
        df_c = df_t.groupby(['BIRIM', 'URUN']).agg({'TUKETIM': 'sum', 'ZAYI': 'sum'}).reset_index()
        res_df = pd.merge(df_c, df_s, on=['BIRIM', 'URUN'], how='outer').fillna(0)

        # Master Data ile eşleştir
        req_cols = ['BIRIM']
        if 'ILCE_MASTER' in birim_master.columns: req_cols.append('ILCE_MASTER')
        if 'TIP_MASTER' in birim_master.columns: req_cols.append('TIP_MASTER')
        if 'UST_BIRIM_MASTER' in birim_master.columns: req_cols.append('UST_BIRIM_MASTER')
        
        res_df = pd.merge(res_df, birim_master[req_cols], on='BIRIM', how='left')

        # Sütunları düzenle
        res_df.rename(columns={
            'ILCE_MASTER': 'Ilce',
            'TIP_MASTER': 'Tip',
            'UST_BIRIM_MASTER': 'Ust_Birim',
            'BIRIM': 'Birim',
            'URUN': 'Urun',
            'TUKETIM': 'Tuketim',
            'ZAYI': 'Zayi',
            'STOK': 'Stok'
        }, inplace=True)

        # Eksik Tip ve İlçeleri doldur
        if 'Ilce' not in res_df.columns: res_df['Ilce'] = 'BILINMIYOR'
        res_df['Ilce'] = res_df['Ilce'].fillna('BILINMIYOR')
        
        if 'Ust_Birim' not in res_df.columns: res_df['Ust_Birim'] = '-'
        res_df['Ust_Birim'] = res_df['Ust_Birim'].fillna('-')

        def infer_tip(row):
            if 'Tip' in res_df.columns and pd.notnull(row.get('Tip')) and str(row.get('Tip')).strip() != '':
                return row['Tip']
            name = str(row['Birim']).upper()
            if 'ASM' in name or 'AILE SAGLIGI' in name: return 'ASM'
            if 'TSM' in name or 'TOPLUM SAGLIGI' in name: return 'TSM'
            if 'ISM' in name: return 'ISM'
            if any(k in name for k in ['HASTANE', 'ÖZEL', 'OZEL', 'GÖÇMEN', 'MÜLTECİ', 'VEREM', 'DISPANSER']): return 'SON KULLANICI'
            return 'Bilinmiyor'
        res_df['Tip'] = res_df.apply(infer_tip, axis=1)

        # HESAPLAMALAR
        res_df['Gunluk_Hiz'] = res_df['Tuketim'] / oto_gun_sayisi
        
        def anomali_tespit(row):
            hiz = row['Gunluk_Hiz']
            tip = str(row['Tip']).upper()
            if 'ASM' in tip and hiz > 30: return True
            elif 'TSM' in tip and hiz > 150: return True
            elif 'SON KULLANICI' in tip and hiz > 150: return True
            elif hiz > 500: return True
            return False
        res_df['Veri_Anomalisi'] = res_df.apply(anomali_tespit, axis=1)

        res_df['Ihtiyac'] = ((res_df['Gunluk_Hiz'] * plan_suresi) * (1 + guvenlik_marji)) - res_df['Stok']
        res_df['Gonderilecek'] = res_df['Ihtiyac'].apply(ozellestirilmis_yuvarlama)
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

        # FİLTRELER
        st.sidebar.markdown("---")
        st.sidebar.markdown("**🔍 Veri Filtreleme**")
        sec_ilce = st.sidebar.multiselect("📍 İlçe Filtrele", options=sorted(res_df['Ilce'].unique()))
        sec_asi = st.sidebar.multiselect("💉 Aşı Filtrele", options=sorted(res_df['Urun'].unique()))
        
        df_f = res_df.copy()
        if sec_ilce: df_f = df_f[df_f['Ilce'].isin(sec_ilce)]
        if sec_asi: df_f = df_f[df_f['Urun'].isin(sec_asi)]

        # METRİKLER VE İL GENELİ HAZIRLIĞI
        df_saha = df_f[~df_f['Tip'].astype(str).str.upper().str.contains('ISM', na=False)]
        df_ism = df_f[df_f['Tip'].astype(str).str.upper().str.contains('ISM', na=False)]

        grp_stok_saha = df_saha.groupby('Urun')['Stok'].sum()
        grp_stok_ism = df_ism.groupby('Urun')['Stok'].sum()
        grp_tuketim_total = df_f.groupby('Urun')['Tuketim'].sum()

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

        if s_tarih: st.info(f"📅 **Dönemsel Tüketim Raporu:** {s_tarih} - {b_tarih} ({oto_gun_sayisi} Gün)")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📦 SEVKİYAT (DOZ)", f"{int(df_f[df_f['Gonderilecek'] > 0]['Gonderilecek'].sum()):,}".replace(",", "."))
        m2.metric("🚨 KRİTİK STOK", len(df_f[df_f['Durum'] == "🚨 KRİTİK"]))
        m3.metric("⚠️ AŞIRI STOK", len(df_f[df_f['Durum'] == "⚠️ AŞIRI"]))
        m4.metric("🏢 KURUM SAYISI", df_f[df_f['Gonderilecek'] > 0]['Birim'].nunique())
        
        st.markdown("---")

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 İl Geneli", "📍 İlçe Bazlı Özet", "📦 Sevkiyat Planı", 
            "⚠️ Fazla ve Ölü Stok", "🔄 Akıllı Transfer", "📉 Zayi ve Verimlilik"
        ])

        with tab1:
            st.subheader("📊 İl Geneli Toplam Stok ve Tüketim Analizi")
            df_genel['İl Ana Depo Yetme Süresi (Gün)'] = df_genel.apply(lambda r: round(r['İl Ana Depo (ISM)'] / r['Günlük ortalama tüketim'], 1) if r['Günlük ortalama tüketim'] > 0 else 999, axis=1)
            df_genel = df_genel.reset_index()
            cols_order = ['Urun', 'İl Geneli Stok', 'İl Ana Depo (ISM)', 'İl Ana Depo Yetme Süresi (Gün)', 'Saha (TSM, ASM, Son)', 'Toplam Tüketim', 'Günlük ortalama tüketim', 'Yetme Süresi (Gün)']
            df_genel = df_genel[cols_order]

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

            try:
                styled_df = df_genel.style.map(highlight_yetme_suresi, subset=['Yetme Süresi (Gün)', 'İl Ana Depo Yetme Süresi (Gün)'])
            except AttributeError:
                styled_df = df_genel.style.applymap(highlight_yetme_suresi, subset=['Yetme Süresi (Gün)', 'İl Ana Depo Yetme Süresi (Gün)'])
            
            styled_df = styled_df.format({"Günlük ortalama tüketim": "{:.2f}", "Yetme Süresi (Gün)": "{:.1f}", "İl Ana Depo Yetme Süresi (Gün)": "{:.1f}", "İl Geneli Stok": "{:.0f}", "İl Ana Depo (ISM)": "{:.0f}", "Saha (TSM, ASM, Son)": "{:.0f}", "Toplam Tüketim": "{:.0f}"})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            c7, c8 = st.columns(2)
            with c7: st.download_button("📥 İl Geneli Excel", to_excel(df_genel), "il_geneli_ozet.xlsx")
            with c8: st.download_button("📥 İl Geneli PDF", to_pdf(df_genel, "Il Geneli Stok ve Tuketim"), "il_geneli_ozet.pdf")

        with tab2:
            df_i = df_f.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            df_i['Ihtiyac'] = (((df_i['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df_i['Stok']
            df_i['Gonderilecek'] = df_i['Ihtiyac'].apply(ozellestirilmis_yuvarlama)

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

        with tab3:
            df_anomali = df_f[(df_f['Veri_Anomalisi'] == True) & (df_f['Gonderilecek'] > 0)].copy()
            if not df_anomali.empty:
                st.error("🚨 **DİKKAT: Olası Hatalı Veri Girişi Tespit Edildi!**")
                st.markdown("Aşağıdaki birimlerin **günlük aşı tüketim hızları** anormal derecede yüksektir. Sevkiyat öncesi teyit ediniz.")
                st.dataframe(df_anomali[['Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Tip', 'Gunluk_Hiz', 'Tuketim', 'Gonderilecek']].style.format({'Gunluk_Hiz': '{:.1f}'}), use_container_width=True)
                st.markdown("---")

            f1_sevk = df_f[df_f['Gonderilecek'] > 0].copy()
            f1_sevk['sort_key'] = f1_sevk['Durum'].map({"🚨 KRİTİK": 0, "✅ Yeterli": 1, "⚠️ AŞIRI": 2})
            f1_sevk = f1_sevk.sort_values(['sort_key', 'Gonderilecek'], ascending=[True, False]).drop('sort_key', axis=1)
            
            st.dataframe(f1_sevk[['Durum', 'Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Tuketim', 'Stok', 'Gonderilecek', 'Yetme_Suresi']], use_container_width=True)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Sevkiyat Excel", to_excel(f1_sevk), "sevkiyat_plani.xlsx")
            with c2: st.download_button("📥 Sevkiyat PDF", to_pdf(f1_sevk, "Sevkiyat Plani"), "sevkiyat_plani.pdf")

        with tab4:
            st.caption(f"{asiri_esik} günden fazla stoğu bulunan 'Aşırı' birimler (ASM ve Son Kullanıcı):")
            f1_asiri = df_f[df_f['Durum'] == "⚠️ AŞIRI"].copy().sort_values('Yetme_Suresi', ascending=False)
            st.dataframe(f1_asiri[['Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Stok', 'Yetme_Suresi']], use_container_width=True)
            c3, c4 = st.columns(2)
            with c3: st.download_button("📥 İade Excel", to_excel(f1_asiri), "asiri_stok.xlsx")
            with c4: st.download_button("📥 İade PDF", to_pdf(f1_asiri, "Asiri Stok"), "asiri_stok.pdf")
            
            st.markdown("---")
            st.subheader("🕸️ Ölü Stok (Hiç Tüketimi Olmayan)")
            f1_olu = df_f[(df_f['Stok'] > 0) & (df_f['Tuketim'] == 0) & (df_f['Tip'].astype(str).str.upper().apply(lambda x: any(k in x for k in ['ASM', 'SON KULLANICI'])))].copy().sort_values('Stok', ascending=False)
            if not f1_olu.empty:
                st.dataframe(f1_olu[['Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Stok']], use_container_width=True)
                c_olu1, c_olu2 = st.columns(2)
                with c_olu1: st.download_button("📥 Ölü Stok Excel", to_excel(f1_olu), "olu_stok.xlsx")
                with c_olu2: st.download_button("📥 Ölü Stok PDF", to_pdf(f1_olu, "Olu Stok"), "olu_stok.pdf")

        with tab5:
            st.subheader("🔄 Akıllı Transfer Önerileri (İlçe İçi)")
            transfer_oncelik = st.radio("Öncelik:", ["Tümü", "Sadece ASM'ler", "Sadece Son Kullanıcı Birimleri"], horizontal=True)
            
            transfer_onerileri = []
            for ilce in df_f['Ilce'].unique():
                df_ilce = df_f[df_f['Ilce'] == ilce]
                df_ilce_transfer = df_ilce[~df_ilce['Tip'].astype(str).str.upper().apply(lambda x: any(k in x for k in ['ISM', 'TSM', 'DEPO']))].copy()
                
                for urun in df_ilce_transfer['Urun'].unique():
                    alicilar = df_ilce_transfer[(df_ilce_transfer['Urun'] == urun) & (df_ilce_transfer['Gonderilecek'] > 0)].copy()
                    if "ASM" in transfer_oncelik: alicilar = alicilar[alicilar['Tip'].astype(str).str.upper().str.contains("ASM")]
                    elif "SON KULLANICI" in transfer_oncelik: alicilar = alicilar[alicilar['Tip'].astype(str).str.upper().str.contains("SON KULLANICI")]
                    
                    vericiler = df_ilce_transfer[(df_ilce_transfer['Urun'] == urun) & (df_ilce_transfer['Fazla_Miktar'] > 0)].copy()
                    
                    if alicilar.empty or vericiler.empty: continue
                    vericiler = vericiler.sort_values('Fazla_Miktar', ascending=False)
                    alicilar = alicilar.sort_values('Gonderilecek', ascending=False)
                    
                    for _, verici in vericiler.iterrows():
                        if verici['Fazla_Miktar'] <= 0: continue
                        for idx_alici, alici in alicilar.iterrows():
                            if alici['Gonderilecek'] <= 0: continue
                            transfer_miktar = min(verici['Fazla_Miktar'], alici['Gonderilecek'])
                            if transfer_miktar >= 10:
                                transfer_onerileri.append({
                                    'İlçe': ilce, 'Ürün': urun, 'Kimden (Verici)': verici['Birim'],
                                    'Kime (Alıcı)': alici['Birim'], 'Transfer Miktarı': int(transfer_miktar)
                                })
                                verici['Fazla_Miktar'] -= transfer_miktar
                                alicilar.at[idx_alici, 'Gonderilecek'] -= transfer_miktar

            if transfer_onerileri:
                df_transfer = pd.DataFrame(transfer_onerileri)
                st.success(f"Toplam {len(df_transfer)} adet (10 Doz+) transfer önerisi bulundu.")
                st.dataframe(df_transfer, use_container_width=True)
                c_tr1, c_tr2 = st.columns(2)
                with c_tr1: st.download_button("📥 Transfer Önerileri Excel", to_excel(df_transfer), "akilli_transfer.xlsx")
                with c_tr2: st.download_button("📥 Transfer Önerileri PDF", to_pdf(df_transfer, "Akilli Transfer Onerileri"), "akilli_transfer.pdf")
            else: st.info("Seçilen kriterlere göre transfer fırsatı bulunamadı.")

        with tab6:
            st.subheader("📉 Zayi ve Verimlilik Analizi")
            
            if not zayi_var_mi:
                st.warning("⚠️ **DİKKAT:** Yüklenen Tüketim Raporunda 'Zayi' sütunu bulunmadığı için analizlerde tüm zayi verileri 0 (sıfır) olarak kabul edilmiştir.")
            
            analiz_turu = st.radio("Analiz Türü:", ("Tüm Aşılar", "Sadece Tekli Doz Aşılar (Kritik)"), horizontal=True)
            df_zayi = df_f.copy()
            if "Tekli" in analiz_turu: df_zayi = df_zayi[~df_zayi['Urun'].str.upper().str.contains('BCG|POLIO|PPD', regex=True)]

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
            st.markdown(f"#### 🏢 En Çok Zayi Veren 20 Kurum")
            kurum_zayi = df_zayi.groupby(['Ilce', 'Birim', 'Urun']).agg({'Zayi': 'sum'}).reset_index()
            kurum_zayi = kurum_zayi[kurum_zayi['Zayi'] > 0].sort_values('Zayi', ascending=False).head(20)
            st.dataframe(kurum_zayi, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Beklenmeyen bir hata oluştu: {e}")
else:
    st.info("Lütfen Tüketim, Stok ve Master Birim listesi dosyalarını yükleyin.")
