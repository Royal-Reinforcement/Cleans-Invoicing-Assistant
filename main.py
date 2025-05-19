import streamlit as st
import pandas as pd
import datetime

import zipfile
import os


st.set_page_config(page_title='Cleans Invoicing Assistant', page_icon='🧍🏻', layout="centered", initial_sidebar_state="auto", menu_items=None)

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

    l, r = st.columns(2)

    today             = datetime.date.today()
    days_since_monday = today.weekday()
    last_week_monday  = today - datetime.timedelta(days=days_since_monday + 7)
    this_week_sunday  = last_week_monday + datetime.timedelta(days=6)

    end_date          = r.date_input('Period End',   value=this_week_sunday)
    start_date        = l.date_input('Period Start', value=last_week_monday)
    date_range        = pd.date_range(start_date, end_date)

    df                = df[df['Completed date'].isin(date_range)]

    cleaners = df['Assignees'].sort_values().unique()

    st.divider()

    st.header('Issues')
    st.success('Coming soon!')

    def grab_issues(row):

        issue = ''

        # Does the task tag contain "RES" or "HLD"?
        if 'RES' in row['Task tags'] or 'HLD' in row['Task tags']:
            if issue == '': issue += 'TAG-ERROR'
            else: issue += ', TAG-ERROR'
        
        # TODO
        

    


    st.divider()

    st.header('Results')

    l, m, r = st.columns(3)

    l.metric(label='Cleans', value=len(df))
    m.metric(label='Cleaners', value=len(df['Assignees'].unique()))
    r.metric(label='Cost', value='$' + str(round(df['Total cost'].sum(), 2)))


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
    
    st.download_button('Download Accounting File', data=df.to_csv(index=False).encode('utf-8'), file_name='Accounting_'+str(start_date)+'_'+str(end_date)+'.csv', type='primary', use_container_width=True)

    st.divider()

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