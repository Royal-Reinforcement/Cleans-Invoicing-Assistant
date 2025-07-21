import streamlit as st
import pandas as pd
import datetime

import smartsheet
import zipfile
import os


@st.cache_data
def smartsheet_to_dataframe(sheet_id):
    smartsheet_client = smartsheet.Smartsheet(st.secrets['smartsheet']['access_token'])
    sheet             = smartsheet_client.Sheets.get_sheet(sheet_id)
    columns           = [col.title for col in sheet.columns]
    rows              = []
    for row in sheet.rows: rows.append([cell.value for cell in row.cells])
    return pd.DataFrame(rows, columns=columns)


def overwrite_reservation_ids(row):
        keywords = ['RES', 'HLD']

        if row['Task tags'] is not None:
            if any(keyword in str(row['Task tags']).upper() for keyword in keywords):
                return row['Task tags']
        
        return row['Reservation ID']


pd.options.mode.chained_assignment = None


st.set_page_config(page_title='Cleans Invoicing Assistant', page_icon='🧍🏻', layout='centered', initial_sidebar_state='auto', menu_items=None)

st.image(st.secrets['logo'], width=100)
st.title('Cleans Invoicing Assistant')
st.info('Use the Breezeway export file to faciliate vendor tasks and highlight any issues.')

file = st.file_uploader(label='breezeway-task-custom-export.csv', type='csv')

if file is not None:

    cleaner_files        = []
    df                   = pd.read_csv(file)
    df['Completed date'] = pd.to_datetime(df['Completed date'])
    df                   = df[['Assignees','Group','Completed date','Property','Task title','Total cost','Rate paid','Task ID','Status','Reservation ID','Task tags']]
    df['Amount due']     = df['Rate paid'].fillna(df['Total cost']).fillna(0.00)
    df['Reservation ID'] = df.apply(overwrite_reservation_ids, axis=1)

    ignore_df            = smartsheet_to_dataframe(st.secrets['smartsheet']['sheet_id']['ignore'])
    ignore_df            = ignore_df.dropna()
    ignore_list          = ignore_df['Vendor'].to_list()

    df                   = df[~df['Assignees'].isin(ignore_list)]

    df.sort_values(by='Completed date', ascending=True, inplace=True)

    
    l, r              = st.columns(2)

    today             = datetime.date.today()
    days_since_monday = today.weekday()
    last_week_monday  = today - datetime.timedelta(days=days_since_monday + 7)
    this_week_sunday  = last_week_monday + datetime.timedelta(days=6)

    end_date          = r.date_input('Period End',   value=this_week_sunday)
    start_date        = l.date_input('Period Start', value=last_week_monday)
    date_range        = pd.date_range(start_date, end_date)

    df                = df[df['Completed date'].isin(date_range)]
    cleaners          = df['Assignees'].sort_values().unique()

    df['Completed date'] = df['Completed date'].dt.strftime('%m/%d/%Y')

    st.divider()

    assignee_df           = df[df['Assignees'].isna()]
    assignee_df['Issue']  = 'Missing_Assignee'

    assignees_df          = df[df['Assignees'].str.contains(';', na=False)]
    assignees_df['Issue'] = 'Multiple_Assignees'

    tag_df                = df[pd.isna(df['Reservation ID'])]
    tag_df['Issue']       = 'Missing_Reservation_Tag'

    statuses              = ['Finished', 'Approved']
    status_df             = df[~df['Status'].isin(statuses)]
    status_df['Issue']    = 'Invalid_Status'

    cost_df               = df[(df['Total cost'].isna() & df['Rate paid'].isna())]
    cost_df['Issue']      = 'Missing_Cost'

    duplicate_df          = df[~pd.isna(df['Reservation ID'])]
    duplicate_df          = duplicate_df[duplicate_df.duplicated(subset=['Reservation ID'], keep=False)]
    duplicate_df['Issue'] = 'Duplicate_Reservation'

    cleans                = smartsheet_to_dataframe(st.secrets['smartsheet']['sheet_id']['cleans'])
    cleans_list           = cleans['Clean'].to_list()
    cleans_df             = df.copy()
    cleans_df['Clean']    = cleans_df['Task title'].str.replace(r'\s*-\s*\(.*?\)$', '', regex=True)
    cleans_df             = cleans_df[~cleans_df['Clean'].isin(cleans_list)]
    cleans_df             = cleans_df.drop(columns=['Clean'])
    cleans_df['Issue']    = 'Invalid_Clean'

    @st.dialog(title='Official Cleans List')
    def show_cleans_list_dialog():
        st.dataframe(cleans, hide_index=True, use_container_width=True)
        with st.expander('Source'):
            st.code('Smartsheet: Cleans \n Workspace: Cleans Invoicing Assistant')

    pricing                 = smartsheet_to_dataframe(st.secrets['smartsheet']['sheet_id']['prices'])
    pricing_df              = df.copy()
    pricing_df['Unit_Code'] = pricing_df['Property'].str.extract(r'\((.*?)\)')
    pricing_df['Clean']     = pricing_df['Task title'].str.replace(r'\s*-\s*\(.*?\)$', '', regex=True)
    pricing_df              = pd.merge(pricing_df, cleans, how='left', on=['Clean'])

    def get_official_amount(row):

        if row['Rate'] not in pricing.columns:
            return None

        result = pricing.loc[pricing['Unit Code'] == row['Unit_Code'], row['Rate']]
        if not result.empty:
            return result.values[0]
        else:
            return None

    pricing_df['Amount']       = pricing_df.apply(get_official_amount, axis=1)
    pricing_df['isRightPrice'] = pricing_df['Amount due'] == pricing_df['Amount']

    def get_pricing_issue(row):
        if pd.isna(row['Amount']):
            if row['Unit_Code'] not in pricing['Unit Code'].values:
                return 'Price_For_Unit_Code_Not_Established'
            if row['Rate'] not in pricing.columns:
                return 'Invalid_Clean'
            return 'Price_Not_Found'
        return 'Price_Set_At_' + str(row['Amount'])
    
    pricing_df['Issue']        = pricing_df.apply(get_pricing_issue, axis=1)
    pricing_df                 = pricing_df[pricing_df['isRightPrice'] == False]
    pricing_df                 = pricing_df.drop(columns=['Unit_Code', 'Clean', 'Rate', 'Amount', 'isRightPrice'])

    issues_df             = pd.concat([assignee_df, assignees_df, tag_df, status_df, cost_df, duplicate_df, cleans_df, pricing_df], ignore_index=True)
    issues_df             = issues_df.sort_values(by='Task ID', ascending=True)
    


    st.header(f"Issues ({issues_df.shape[0]})", help='A 8-point inspection of each task to ensure: (1) there is an assignee, (2) there is only one assignee, (3) the task has a reservation number or is tagged with a reservation number, (4) the status is either Finished or Approved, (5) there is a cost, (6) there are not duplicate reservation numbers, (7) the clean type is in the official cleans list, and (8) pricing matches the established, property-specific rates. If any of these conditions are not met, the task will be flagged below for review.')

    if issues_df.shape[0] != 0:

        if assignee_df.shape[0] != 0:
            with st.expander(f"There are **{assignee_df.shape[0]}** tasks with **no assignee**."):
                st.dataframe(assignee_df, hide_index=True, use_container_width=True)
        
        if assignees_df.shape[0] != 0:
            with st.expander(f"There are **{assignees_df.shape[0]}** tasks with **multiple assignees**."):
                st.dataframe(assignees_df, hide_index=True, use_container_width=True)
        
        if cost_df.shape[0] != 0:
            with st.expander(f"There are **{cost_df.shape[0]}** tasks that do not have a **Total cost** or **Rate paid**."):
                st.dataframe(cost_df, hide_index=True, use_container_width=True)
        
        if tag_df.shape[0] != 0:
            with st.expander(f"There are **{tag_df.shape[0]}** tasks that do not have a **reservation number**."):
                st.dataframe(tag_df, hide_index=True, use_container_width=True)
        
        if status_df.shape[0] != 0:
            with st.expander(f"There are **{status_df.shape[0]}** tasks with a **status** that is not **Finished** or **Approved**."):
                st.dataframe(status_df, hide_index=True, use_container_width=True)
        
        if duplicate_df.shape[0] != 0:
            with st.expander(f"There are **{duplicate_df.shape[0]}** tasks with reused **reservation numbers**."):
                st.dataframe(duplicate_df, hide_index=True, use_container_width=True)
        
        if cleans_df.shape[0] != 0:
            with st.expander(f"There are **{cleans_df.shape[0]}** tasks that have titles not in the **official cleans list**."):
                st.dataframe(cleans_df, hide_index=True, use_container_width=True)
                if st.button('Official Cleans List', on_click=lambda: st.write(cleans_list), type='secondary', use_container_width=True):
                    show_cleans_list_dialog()

        if pricing_df.shape[0] != 0:
            with st.expander(f"There are **{pricing_df.shape[0]}** tasks that have an **invalid price**."):
                st.dataframe(pricing_df, hide_index=True, use_container_width=True)

        st.download_button(
            label='Download Issues File',
            data=issues_df.to_csv(index=False).encode('utf-8'),
            file_name='Issues_'+str(start_date)+'_'+str(end_date)+'.csv',
            mime='text/csv',
            use_container_width=True,
            type='primary'
        )
    
    else:
        st.success('There are no issues for this date range!')


    st.divider()

    
    st.header('Results')

    tab1, tab2 = st.tabs(['🏘️ Housekeeping', '💵 Accounting'])

    with tab1:

        l, m, r = st.columns(3)

        l.metric(label='Cleans', value=len(df))
        m.metric(label='Properties', value=len(df['Property'].unique()))
        r.metric(label='Cleaners', value=len(df['Assignees'].unique()))


        for cleaner in cleaners:
            df_cleaner = df[df['Assignees'] == cleaner]
            cleaner_files.append(df_cleaner)
            
        with zipfile.ZipFile('cleaners.zip', 'w') as izip:
            for cleaner_file in cleaner_files:
                vdf = cleaner_file.reset_index()
                vdf = vdf.drop(columns=['index'])

                if len(vdf) > 0:
                    file_name = vdf['Assignees'][0]
                    vdf.to_csv(f'{file_name}.csv', index=False)
                    izip.write(f'{file_name}.csv')
                    os.remove(f'{file_name}.csv')
        
        with open('cleaners.zip','rb') as invoice_file:
            st.download_button('Download Cleaner Files', data=invoice_file, file_name='Cleaners_'+str(start_date)+'_'+str(end_date)+'.zip', type='primary', use_container_width=True)

        with st.expander('Cleaners'):
            
            for cleaner in cleaners:
                df_cleaner = df[df['Assignees'] == cleaner]

                if len(df_cleaner) > 0:
                    st.subheader(cleaner)

                    l, m, r = st.columns(3)

                    st.dataframe(df_cleaner, hide_index=True, use_container_width=True)
                    st.download_button(
                        label='Download ' + cleaner + ' CSV',
                        data=df_cleaner.to_csv(index=False).encode('utf-8'),
                        file_name=(cleaner).strip() + '.csv',
                        mime='text/csv',
                        use_container_width=True,
                        type='primary'
                    )
    
    with tab2:

        current_year = datetime.datetime.now().year
        prior_year   = current_year - 1
        report_url   = f"{st.secrets['escapia_1']}{prior_year}{st.secrets['escapia_2']}{current_year}{st.secrets['escapia_3']}"
        
        st.link_button('Download the **Housekeeping Report** from **Escapia**', url=report_url, type='secondary', use_container_width=True, help='Housekeeping Arrival Departure Report - Excel 1 line')

        escapia_file = st.file_uploader(label='Housekeeping Arrival Departure Report - Excel 1 line.csv', type='csv')

        if escapia_file is not None:

            escapia_df = pd.read_csv(escapia_file)
            escapia_df = escapia_df[['Unit_Code', 'Reservation_Number', 'ReservationTypeDescription']]

            df['Reservation ID'] = df['Reservation ID'].str.replace(' ','', regex=False)

            accounting_df            = pd.merge(df, escapia_df, how='left', left_on='Reservation ID', right_on='Reservation_Number')
            accounting_df['Address'] = accounting_df['Property'].str.split('-').str[1].str.strip()

            def build_description(row):
                if pd.isna(row['Reservation_Number']):
                    return 'NEED'
                
                return f"{row['Reservation_Number']}, {row['Address']}"

            def build_category(row):
                if pd.isna(row['ReservationTypeDescription']):
                    return 'NEED'
                
                if row['ReservationTypeDescription'] == 'Renter':
                    return st.secrets['category']['guest']
                elif row['ReservationTypeDescription'] == 'Owner' or row['ReservationTypeDescription'] == 'Guest of Owner':
                    return st.secrets['category']['owner']

            accounting_df['Description'] = accounting_df.apply(build_description, axis=1)
            accounting_df['Category']    = accounting_df.apply(build_category, axis=1)

            today  = datetime.datetime.today()
            monday = today - datetime.timedelta(days=today.weekday())
            friday = monday + datetime.timedelta(days=4)

            accounting_file = pd.DataFrame()
            accounting_file['Vendor']                = accounting_df['Assignees']
            accounting_file['Class']                 = accounting_df['Unit_Code']
            accounting_file['Description']           = accounting_df['Description']
            accounting_file['Category']              = accounting_df['Category']
            accounting_file['Unit Price']            = accounting_df['Amount due'].astype(float)
            accounting_file['Transaction Type']      = 'Bill'
            accounting_file['Qty']                   = 1.00
            accounting_file['Invoice/Bill Date']     = today.strftime('%-m/%-d/%y')
            accounting_file['Due Date']              = friday.strftime('%-m/%-d/%y')
            accounting_file['Invoice / Bill Number'] = monday.strftime('%-m.%-d.%y')
            accounting_file['Customer']              = ''
            accounting_file['Currency Code']         = ''
            accounting_file['Product/Services']      = ''
            accounting_file['Discount %']            = ''
            accounting_file['Location']              = ''
            accounting_file['Tax']                   = ''

            cleaner_map     = smartsheet_to_dataframe(st.secrets['smartsheet']['sheet_id']['cleaners'])
            cleaner_map.loc[cleaner_map['Breezeway'] == st.secrets.cleaners.issue, 'Breezeway'] = st.secrets.cleaners.fix

            accounting_file = pd.merge(accounting_file, cleaner_map, left_on='Vendor', right_on='Breezeway', how='left')
            accounting_file = accounting_file.drop(['Vendor','Breezeway'], axis=1)
            accounting_file.rename(columns={'Quickbooks': 'Vendor'}, inplace=True)

            accounting_file = accounting_file[['Invoice/Bill Date', 'Due Date', 'Invoice / Bill Number', 'Transaction Type', 'Customer', 'Vendor', 'Currency Code', 'Product/Services', 'Description', 'Qty', 'Discount %', 'Unit Price', 'Category', 'Location', 'Class', 'Tax']]
            accounting_file = accounting_file.sort_values(by='Vendor', ascending=True)


            l, m, r = st.columns(3)

            l.metric(label='Cleans', value=len(df))
            m.metric(label='Cleaners', value=len(df['Assignees'].unique()))
            r.metric(label='Amount', value='$' + str(round(df['Amount due'].sum(), 2)), help='Assumes **Rate paid** if present, **Total cost** otherwise.')

            st.download_button('Download Accounting File', data=accounting_file.to_csv(index=False).encode('utf-8'), file_name='Accounting_'+str(start_date)+'_'+str(end_date)+'.csv', type='primary', use_container_width=True)
            
            with open('cleaners.zip','rb') as invoice_file:
                st.download_button('Download Cleaner Files', data=invoice_file, file_name='Cleaners_'+str(start_date)+'_'+str(end_date)+'.zip', type='primary', use_container_width=True, key='two')