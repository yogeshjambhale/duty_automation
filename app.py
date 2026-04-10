import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import os

# ==========================================
# 1. UI & SESSION STATE SETUP
# ==========================================
st.set_page_config(page_title="Aurafox Billing Tool", layout="wide")
st.title("Duty Closing Tool")
st.write("Professional Automation for Aurafox Solutions Pvt. Ltd.")

if 'index' not in st.session_state: st.session_state.index = 0
if 'data' not in st.session_state: st.session_state.data = None
if 'fail_log' not in st.session_state: st.session_state.fail_log = []

profile_path = os.path.join(os.getcwd(), "fleetoz_chrome_profile")

# ==========================================
# 2. SELF-HEALING BROWSER LOGIC
# ==========================================
@st.cache_resource
def get_driver():
    options = Options()
    options.add_argument(f"user-data-dir={profile_path}")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false")
    return webdriver.Chrome(options=options)

def get_active_driver():
    try:
        driver = get_driver()
        driver.current_window_handle 
        return driver
    except:
        st.cache_resource.clear()
        return get_driver()

# ==========================================
# 3. SIDEBAR: DATA MANAGEMENT
# ==========================================
with st.sidebar:
    st.header("Batch Management")
    uploaded_file = st.file_uploader("Upload CUSTOMER_MIS_REPORT.csv", type="csv")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.session_state.data = df.to_dict('records')
        st.success(f"📂 {len(df)} Duties Loaded")

    if st.button("♻️ Reset Entire Batch"):
        st.session_state.index = 0
        st.session_state.fail_log = []
        st.rerun()

# ==========================================
# 4. MAIN AUTOMATION HUB
# ==========================================
if st.session_state.data:
    current_batch = st.session_state.data
    idx = st.session_state.index

    if idx < len(current_batch):
        duty = current_batch[idx]
        st.write(f"### 📍 Task {idx + 1} of {len(current_batch)}: **{duty['Duty_ID']}**")
        
        cols = st.columns(4)
        cols[0].metric("Travel Date", duty['Travel_Date'])
        cols[1].metric("Garage KM", f"{duty['Garage_Start_KM']} - {duty['Garage_End_KM']}")
        cols[2].metric("Duty KM", f"{duty['Duty_Start_KM']} - {duty['Duty_End_KM']}")
        cols[3].metric("Toll Amount", duty['Toll_Amount'])

        st.divider()

        # --- STEP 1: SEARCH ---
        if st.button("🔍 Step 1: Search & Filter ID"):
            try:
                driver = get_active_driver()
                if "billing" not in driver.current_url:
                    driver.get("https://web.fleetoz.com/billing")
                driver.maximize_window()
                
                # 15-second wait for slow PC rendering [cite: 7]
                st.write("⏳ Waiting 15 seconds for dashboard to load...")
                time.sleep(15) 

                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])

                search_bar = None
                selectors = [(By.XPATH, "//input[contains(@placeholder, 'Booking ID')]"), (By.CSS_SELECTOR, "input[placeholder*='Booking ID']")]
                for by, sel in selectors:
                    els = driver.find_elements(by, sel)
                    for el in els:
                        if el.is_displayed():
                            search_bar = el; break
                    if search_bar: break
                
                if search_bar:
                    driver.execute_script("arguments[0].value='';", search_bar)
                    time.sleep(1); search_bar.send_keys(str(duty['Duty_ID']))
                    time.sleep(1); search_bar.send_keys(Keys.ENTER)
                    st.success(f"✅ Filtered {duty['Duty_ID']}. Open the form now!")
                else:
                    st.error("Search bar not detected. Refreshing...")
                    driver.refresh()
            except Exception as e:
                st.error(f"Search failed: {e}")

        # --- STEP 2: INJECT, SAVE & CLOSE ---
        if st.button("⚡ Step 2: Inject, Save & Close Duty"):
            try:
                driver = get_active_driver()
                
                js_payload = f"""
                    function setReactValue(el, val) {{
                        if (!el) return;
                        let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, val);
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}

                    // Fill Table Data
                    document.querySelectorAll('tr').forEach(row => {{
                        let text = row.innerText.trim();
                        let dateInput = row.querySelector('input[type="date"]');
                        let inputs = row.querySelectorAll('input[type="text"], input[type="number"]');
                        if(text.includes('Garage Start')) {{
                            setReactValue(dateInput, '{duty['Travel_Date']}');
                            setReactValue(inputs[0], '{duty['Garage_Start_Time']}');
                            setReactValue(inputs[1], '{duty['Garage_Start_KM']}');
                        }} else if(text.includes('Duty Start')) {{
                            setReactValue(dateInput, '{duty['Travel_Date']}');
                            setReactValue(inputs[0], '{duty['Duty_Start_Time']}');
                            setReactValue(inputs[1], '{duty['Duty_Start_KM']}');
                        }} else if(text.includes('Duty End')) {{
                            setReactValue(dateInput, '{duty['Travel_Date']}');
                            setReactValue(inputs[0], '{duty['Duty_End_Time']}');
                            setReactValue(inputs[1], '{duty['Duty_End_KM']}');
                        }} else if(text.includes('Garage End')) {{
                            setReactValue(dateInput, '{duty['Travel_Date']}');
                            setReactValue(inputs[0], '{duty['Garage_End_Time']}');
                            setReactValue(inputs[1], '{duty['Garage_End_KM']}');
                        }}
                    }});

                    // Toll Injection
                    document.querySelectorAll('[data-accordion-component="Accordion"]').forEach(acc => {{
                        let name = acc.querySelector('input[placeholder="Item Name"]');
                        if(name) setReactValue(name, 'Toll');
                        acc.querySelectorAll('label').forEach(lbl => {{
                            if(lbl.innerText.trim() === 'Price') setReactValue(lbl.parentElement.querySelector('input'), '{duty['Toll_Amount']}');
                        }});
                    }});

                    // Fetch Prices
                    setTimeout(() => {{
                        document.querySelectorAll('button').forEach(b => {{ if(b.innerText.trim() === 'Get Price') b.click(); }});
                    }}, 1000);
                """
                driver.execute_script(js_payload)
                
                # Buffer for API Price Fetching
                time.sleep(5) 
                
                # NEW: Final Step - Add Charges, SAVE and CLOSE 
                driver.execute_script("""
                    // 1. Add All Charges
                    document.querySelectorAll('button').forEach(b => { 
                        if(b.innerText.trim() === 'Add All Charges') b.click(); 
                    });
                    
                    // 2. Click Save Buttons (Both Purchase and Sales) 
                    setTimeout(() => {
                        document.querySelectorAll('button').forEach(b => {
                            if(b.innerText.trim() === 'Save' && b.classList.contains('bg-green-600')) {
                                b.scrollIntoView({block: 'center'});
                                b.click();
                            }
                        });
                    }, 2000);

                    // 3. Click Close Button or X icon 
                    setTimeout(() => {
                        let closeBtn = document.querySelector('button.bg-red-600') || document.querySelector('div.bg-white button.text-gray-500');
                        if(closeBtn) closeBtn.click();
                    }, 4000);
                """)
                
                st.session_state.index += 1
                st.toast(f"✅ Duty {duty['Duty_ID']} Saved & Closed!")
                time.sleep(1)
                st.rerun()

            except Exception as e:
                st.session_state.fail_log.append({"Duty_ID": duty['Duty_ID'], "Error": str(e)})
                st.error(f"❌ Error: {e}")

        if st.button("Skip This Duty"):
            st.session_state.index += 1
            st.rerun()
    else:
        st.balloons(); st.success("🎉 Batch Complete!")
    if st.session_state.fail_log:
        with st.expander("📋 Failure Log"): st.table(st.session_state.fail_log)
else:
    st.info("👋 Please upload a CSV to begin.")