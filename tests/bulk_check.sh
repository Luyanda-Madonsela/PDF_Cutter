API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)/api
for f in sample_memo.pdf sample_addendum.pdf sample_paper.pdf sample_errata.pdf; do curl -s -o /dev/null -F "file=@$f" $API/jobs; done
for i in $(seq 1 60); do sleep 5; C=$(curl -s $API/sets | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['counts'], [(s['status'],[(x['doc_type'],x['status']) for x in s['docs']]) for s in d['sets']])"); echo "$C"; echo "$C" | grep -q "'processing': 0" && echo "$C" | grep -q "'sorting': 0" && echo "$C" | grep -q "'done': 1" && break; done
SID=$(curl -s $API/sets | python3 -c "import sys,json;print(json.load(sys.stdin)['sets'][0]['id'])")
curl -s $API/sets/$SID | python3 -c "
import sys,json;d=json.load(sys.stdin);print(d['base_name'],d['meta'],d['flagged'])
qp=[x for x in d['documents'] if x['meta']['doc_type']=='question_paper'][0]
for x in d['documents']: print(x['meta']['doc_type'],x['status'],x.get('error'),[(q['label'],q['marks'],q['width'],q['height'],q['flags']) for q in x['questions']])
for q in qp['questions']: l=d['links'][q['id']]; print(q['filename'], bool(l['memo']), len(l['addenda']), len(l['errata']), l['flags'])
print(d['extras'])"
curl -s -o /app/tests/out/set.zip $API/sets/$SID/zip && unzip -l /app/tests/out/set.zip
