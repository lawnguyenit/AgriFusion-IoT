"""Official Household235 intake, strict minute-to-hour aggregation and provenance."""
from pathlib import Path
import zipfile,urllib.request
import numpy as np
import pandas as pd
from .journal import write,sha


def aggregate(frame):
    """No partial-bin averaging or interpolation; duplicate minutes invalidate hour."""
    d=frame.copy()
    if d.timestamp.isna().any():raise ValueError('Unparseable minute timestamp')
    d['hour']=d.timestamp.dt.floor('h');d['valid']=np.isfinite(d.value)&(d.value>=0)&(d.timestamp.dt.second==0)
    d['duplicate']=d.timestamp.duplicated(keep=False)
    d['raw_row']=np.arange(len(d),dtype=np.int64)
    g=d.groupby('hour',sort=True)
    hours=g.agg(raw_rows=('value','size'),unique_minutes=('timestamp','nunique'),valid_minutes=('valid','sum'),duplicate_rows=('duplicate','sum'),
                raw_row_start=('raw_row','min'),raw_row_end=('raw_row','max'),mean_candidate=('value','mean'))
    valid=(hours.raw_rows==60)&(hours.unique_minutes==60)&(hours.valid_minutes==60)&(hours.duplicate_rows==0)
    hours['value']=hours.mean_candidate.where(valid)
    grid=pd.date_range(hours.index.min(),hours.index.max(),freq='h')
    hours=hours.reindex(grid);hours.index.name='timestamp';hours=hours.reset_index()
    hours['timestamp']=hours.timestamp.astype('int64');hours['entity']='household235'
    hours['sample_id']=['household235::'+str(t) for t in hours.timestamp]
    hours['invalid_hour']=~np.isfinite(hours.value)
    return hours.drop(columns='mean_candidate')


def acquire(journal):
    config=journal.protocol['confirmation'];raw=journal.root/'raw';raw.mkdir(exist_ok=True)
    archive=raw/'household235_source.zip'
    if not archive.exists():
        temporary=raw/'download.tmp'
        with urllib.request.urlopen(config['url'],timeout=180) as stream,temporary.open('wb') as out:
            while data:=stream.read(1024*1024):out.write(data)
        temporary.replace(archive)
    with journal.unit('source_audit','household235',['canonical_hourly.csv','source_manifest.json'],[archive]) as (out,reused):
        if not reused:
            with zipfile.ZipFile(archive) as z:
                names=[n for n in z.namelist() if Path(n).name=='household_power_consumption.txt']
                if len(names)!=1:raise ValueError('Unexpected source member')
                with z.open(names[0]) as f:
                    d=pd.read_csv(f,sep=';',usecols=['Date','Time','Global_active_power'],dtype=str)
            timestamp=pd.to_datetime(d.Date+' '+d.Time,format='%d/%m/%Y %H:%M:%S',errors='raise')
            values=pd.to_numeric(d.Global_active_power,errors='coerce')
            frame=aggregate(pd.DataFrame({'timestamp':timestamp,'value':values}))
            frame['raw_archive_sha256']=sha(archive);frame.to_csv(out/'canonical_hourly.csv',index=False)
            write(out/'source_manifest.json',{'source_url':config['url'],'source_page':'https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption',
                  'citation':'Hebrail, G. & Berard, A. (2006). DOI:10.24432/C58K54. UCI ML Repository. CC BY 4.0.',
                  'archive_sha256':sha(archive),'raw_rows':len(d),'missing_or_invalid_values':int((~np.isfinite(values)|(values<0)).sum()),
                  'duplicate_timestamp_rows':int(timestamp.duplicated(keep=False).sum()),'hourly_rows':len(frame),
                  'unknown_hourly_bins':int(frame.invalid_hour.sum()),'hour_rule':config['hour_rule'],'clock':config['clock'],
                  'raw_dependency_mapping':'0-based member row indexes; hourly raw_row_start/end and raw_rows/unique_minutes/valid_minutes; no reuse across hourly bins',
                  'physical_event_truth':False})
    return out
