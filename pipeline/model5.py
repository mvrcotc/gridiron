exec(open('model4.py').read().split("print('calibrating")[0])
import numpy as np, json
print('extending the search past the grid edge\n')
best=None
for vol in (1.8,2.3,3.0,4.0):
    for ysh in (0.3,0.38,0.45):
        infl={'vol':vol,'yshape':ysh}
        pit=backtest(infl)
        h,_=np.histogram(pit,bins=10,range=(0,1)); h=h/h.sum()
        dev=float(np.abs(h-0.1).sum())
        if best is None or dev<best[0]: best=(dev,infl,h)
        print(f'  vol x{vol:<4} yshape {ysh:<5} -> calibration error {dev:.3f}')
dev,infl,h=best
print(f'\nchosen: {infl}   calibration error {dev:.3f}')
print('\nPIT histogram (10% per decile is perfect):')
for i,v in enumerate(h):
    print(f'  {i*10:>3}-{i*10+10:<3}%  {v*100:5.1f}%  '+'#'*int(round(v*200)))
json.dump({'infl':infl,'pit':[float(x) for x in h],'dev':dev},open('fit_cal.json','w'))
