"""Persistently count actual supervised fit invocations before execution."""
from contextlib import ExitStack
from unittest.mock import patch
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from .journal import read,write


class FitBudget:
    def __init__(self,root,limit=36):
        self.path=root/'SUPERVISED_FIT_BUDGET.json';self.limit=limit
        self.record=read(self.path) if self.path.exists() else {'maximum':limit,'attempted':0,'calls':[]}
        if self.record['maximum']!=limit:raise ValueError('Fit budget lock changed')

    def __enter__(self):
        self.stack=ExitStack()
        for cls in (HistGradientBoostingClassifier,LogisticRegression):
            original=cls.fit;budget=self
            def wrapped(model,*args,_original=original,**kwargs):
                if budget.record['attempted']>=budget.limit:raise RuntimeError('Predeclared supervised-fit budget exhausted')
                budget.record['attempted']+=1;budget.record['calls'].append(type(model).__name__);write(budget.path,budget.record)
                return _original(model,*args,**kwargs)
            self.stack.enter_context(patch.object(cls,'fit',wrapped))
        return self

    def __exit__(self,*args):return self.stack.__exit__(*args)
