from pathlib import Path
from tempfile import TemporaryDirectory
import io
import json
import unittest
import zipfile
import numpy as np
import pandas as pd
from ..sources import read_beijing, read_appliances
from ..preparation import prepare_frame, segments_from_frame


class SourceTests(unittest.TestCase):
    def test_Appliances_requires_six_slots_and_uses_bin_end(self):
        with TemporaryDirectory() as td:
            path = Path(td)/'source.csv'
            times = pd.date_range('2020-01-01', periods=12, freq='10min').delete(7)
            pd.DataFrame({'date':times, 'RH_1':np.arange(len(times))+30}).to_csv(path,index=False)
            frame, info = read_appliances(path)
            self.assertEqual(len(frame),2)
            self.assertEqual(frame.timestamp.iloc[0], pd.Timestamp('2020-01-01 01:00').value)
            self.assertTrue(np.isfinite(frame.value.iloc[0]));self.assertTrue(np.isnan(frame.value.iloc[1]))
            self.assertLess(frame.source_max_timestamp.iloc[0], frame.timestamp.iloc[0])
            self.assertEqual(info['incomplete_bins'],1)

    def test_Appliances_rejects_duplicate_source_time(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'source.csv'
            pd.DataFrame({'date':['2020-01-01','2020-01-01'],'RH_1':[50,60]}).to_csv(path,index=False)
            with self.assertRaises(ValueError):read_appliances(path)

    def test_nested_PRSA_selection_does_not_ingest_example_CSV(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'outer.zip'; nested=io.BytesIO()
            payload='year,month,day,hour,station,PM2.5\n2013,3,1,0,station1,12\n'
            with zipfile.ZipFile(nested,'w') as z:z.writestr('PRSA_Data_station1_20130301-20170228.csv',payload)
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('PRSA2017_Data_20130301-20170228.zip',nested.getvalue())
                z.writestr('data.csv','wrong,example\n1,2\n')
            frame,info=read_beijing(path,expected_station_count=1)
            self.assertEqual(len(frame),1);self.assertEqual(frame.value.iloc[0],12)
            self.assertEqual(len(info['members']),1)

    def test_four_way_splits_share_times_and_exclude_real_gaps(self):
        cfg={'splits':{'fractions_of_sorted_unique_source_times':[.6,.15,.125,.125]},
             'time_grid_and_target':{'K':3,'warmup_per_segment':24,'threshold':{'quantile':.75}}}
        rows=[]
        for station in ('a','b'):
            for i,t in enumerate(pd.date_range('2020-01-01',periods=1200,freq='h')):
                # Positive values in the upper quartile form runs of length 3.
                value=float(i%20)
                rows.append({'sample_id':f'{station}:{i}','entity':station,'timestamp':t.value,
                             'value':value,'source_rows':json.dumps([f'{station}:raw:{i}'])})
        frame=pd.DataFrame(rows);frame.loc[650,'value']=np.nan
        data,segs,support,meta=prepare_frame(frame,cfg)
        self.assertTrue(meta['hard_gate_passed'])
        self.assertEqual(data.groupby('timestamp').partition.nunique().max(),1)
        self.assertEqual(sum(r['genuinely_missing_reference_rows'] for r in support),1)
        for s in segs:
            self.assertFalse(s.score[:24].any())
            self.assertEqual(len(set(s.keys)),len(s.keys))
        restored=segments_from_frame(data)
        self.assertEqual([s.segment_id for s in segs],[s.segment_id for s in restored])

    def test_raw_dependencies_cannot_cross_partitions(self):
        cfg={'splits':{'fractions_of_sorted_unique_source_times':[.6,.15,.125,.125]},
             'time_grid_and_target':{'K':3,'warmup_per_segment':24,'threshold':{'quantile':.75}}}
        rows=[{'sample_id':str(i),'entity':'a','timestamp':pd.Timestamp('2020-01-01').value+i*3600*10**9,
               'value':i%20,'source_rows':json.dumps(['reused' if i in (0,800) else str(i)])} for i in range(1000)]
        with self.assertRaisesRegex(ValueError,'crosses partitions'):prepare_frame(pd.DataFrame(rows),cfg)
