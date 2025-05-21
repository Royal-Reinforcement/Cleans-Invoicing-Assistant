import streamlit as st
import pandas as pd
import datetime

import zipfile
import os


pd.options.mode.chained_assignment = None


st.set_page_config(page_title='Cleans Invoicing Assistant', page_icon='🧍🏻', layout='centered', initial_sidebar_state='auto', menu_items=None)

st.image(st.secrets['logo'], width=100)
st.title('Cleans Invoicing Assistant')
st.info('Use the Breezeway export file to faciliate vendor tasks and highlight any issues.')

with st.expander('Uploaded Files'):
    
    file_descriptions = [
        ['breezeway-task-custom-export.csv','Breezeway > Tasks > Cleans > Cleans (Invoicing) > {Select All} > Export to CSV'],
    ]

    files = {
        'breezeway-task-custom-export.csv': None,
    }

    uploaded_files = st.file_uploader(
        label='Files (' + str(len(files)) + ')',
        accept_multiple_files=True
    )

    st.info('File names are **case sensitive** and **must be identical** to the file name below.')
    st.dataframe(pd.DataFrame(file_descriptions, columns=['Required File','Source Location']), hide_index=True, use_container_width=True)


if len(uploaded_files) > 0:
    for index, file in enumerate(uploaded_files):
        files[file.name] = index

    hasAllRequiredFiles = True
    missing = []

    for file in files:
        if files[file] == None:
            hasAllRequiredFiles = False
            missing.append(file)


if len(uploaded_files) > 0 and not hasAllRequiredFiles:
    for item in missing:
        st.warning('**' + item + '** is missing and required.')


elif len(uploaded_files) > 0 and hasAllRequiredFiles:

    vendor_files   = []
    df             = pd.read_csv(uploaded_files[files['breezeway-task-custom-export.csv']])
    df['Completed date'] = pd.to_datetime(df['Completed date'])
    df.sort_values(by='Completed date', ascending=True, inplace=True)

    df = df[[
        'Assignees',
        'Group',
        'Completed date',
        'Property',
        'Task title',
        'Total cost',
        'Rate paid',
        'Task ID',
        'Status',
        'Task tags',
        ]]
    
    df['Amount due'] = df['Rate paid'].fillna(df['Total cost']).fillna(0.00)

    l, r = st.columns(2)

    today             = datetime.date.today()
    days_since_monday = today.weekday()
    last_week_monday  = today - datetime.timedelta(days=days_since_monday + 7)
    this_week_sunday  = last_week_monday + datetime.timedelta(days=6)

    end_date          = r.date_input('Period End',   value=this_week_sunday)
    start_date        = l.date_input('Period Start', value=last_week_monday)
    date_range        = pd.date_range(start_date, end_date)

    df                = df[df['Completed date'].isin(date_range)]

    cleaners          = df['Assignees'].sort_values().unique()

    st.divider()


    tags                 = ['RES', 'HLD']
    tag_pattern          = '|'.join(tags)
    tag_df               = df[~df['Task tags'].str.contains(tag_pattern, case=False, na=False)]
    tag_df['Issue']      = 'Missing_Reservation_Tag'

    statuses             = ['Finished', 'Approved']
    status_df            = df[~df['Status'].isin(statuses)]
    status_df['Issue']   = 'Invalid_Status'

    assignee_df          = df[df['Assignees'].isna()]
    assignee_df['Issue'] = 'Missing_Assignee'

    cost_df              = df[(df['Total cost'].isna() & df['Rate paid'].isna())]
    cost_df['Issue']     = 'Missing_Cost'

    duplicate_df          = df[df['Task tags'].str.contains(tag_pattern, case=False, na=False)]
    duplicate_df          = duplicate_df[duplicate_df.duplicated(subset=['Task tags'], keep=False)]
    duplicate_df['Issue'] = 'Duplicate_Reservation'


    issues_df = pd.concat([assignee_df, tag_df, status_df, cost_df, duplicate_df], ignore_index=True)
    issues_df = issues_df.sort_values(by='Task ID', ascending=True)


    st.header(f"Issues ({issues_df.shape[0]})", help='A 5-point inspection of each task to ensure: (1) there is an assignee, (2) the task is tagged with a reservation number, (3) the status is either Finished or Approved, (4) there is a cost, and (5) there are not duplicate reservation numbers. If any of these conditions are not met, the task will be flagged below for review.')

    if issues_df.shape[0] != 0:

        if assignee_df.shape[0] != 0:
            with st.expander(f"There are **{assignee_df.shape[0]}** tasks with **no assignee**."):
                st.dataframe(assignee_df, hide_index=True, use_container_width=True)
        
        if cost_df.shape[0] != 0:
            with st.expander(f"There are **{cost_df.shape[0]}** tasks that do not have a **Total cost** or **Rate paid**."):
                st.dataframe(cost_df, hide_index=True, use_container_width=True)
        
        if tag_df.shape[0] != 0:
            with st.expander(f"There are **{tag_df.shape[0]}** tasks which **tags** do not include **RES** or **HLD**."):
                st.dataframe(tag_df, hide_index=True, use_container_width=True)
        
        if status_df.shape[0] != 0:
            with st.expander(f"There are **{status_df.shape[0]}** tasks with a **status** that is not **Finished** or **Approved**."):
                st.dataframe(status_df, hide_index=True, use_container_width=True)
        
        if duplicate_df.shape[0] != 0:
            with st.expander(f"There are **{duplicate_df.shape[0]}** tasks with reused **reservation numbers**."):
                st.dataframe(duplicate_df, hide_index=True, use_container_width=True)

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
            vendor_files.append(df_cleaner)
            
        with zipfile.ZipFile('cleaners.zip', 'w') as izip:
            for vendor_file in vendor_files:
                vdf = vendor_file.reset_index()
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

        l, m, r = st.columns(3)

        l.metric(label='Cleans', value=len(df))
        m.metric(label='Cleaners', value=len(df['Assignees'].unique()))
        r.metric(label='Amount', value='$' + str(round(df['Amount due'].sum(), 2)), help='Assumes **Rate paid** if present, **Total cost** otherwise.')

        st.download_button('Download Accounting File', data=df.to_csv(index=False).encode('utf-8'), file_name='Accounting_'+str(start_date)+'_'+str(end_date)+'.csv', type='primary', use_container_width=True)