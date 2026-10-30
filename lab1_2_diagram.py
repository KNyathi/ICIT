
import argparse
import csv
import json
import math
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from xml.sax.saxutils import escape as xe

STATIONERY = [
    ['ручка','тетрадь','карандаш'],
    ['ручка','тетрадь','ластик'],
    ['карандаш','линейка','ластик'],
    ['ручка','тетрадь','карандаш','ластик'],
    ['тетрадь','линейка'],
    ['ручка','карандаш'],
    ['ручка','тетрадь','линейка'],
    ['тетрадь','ластик','линейка'],
    ['ручка','тетрадь','карандаш'],
    ['карандаш','ластик'],
    ['ручка','тетрадь'],
    ['ручка','карандаш','линейка'],
    ['тетрадь','карандаш','ластик'],
    ['ручка','тетрадь','ластик'],
    ['ручка','линейка'],
    ['тетрадь','карандаш'],
    ['ручка','тетрадь','карандаш','линейка'],
    ['ластик','линейка'],
    ['ручка','тетрадь','карандаш'],
    ['тетрадь','ластик'],
    ['ручка','карандаш','ластик'],
    ['ручка','тетрадь','линейка'],
    ['карандаш','линейка'],
    ['ручка','тетрадь','карандаш','ластик'],
    ['тетрадь','линейка','ластик'],
    ['ручка','карандаш'],
    ['ручка','тетрадь','карандаш'],
    ['тетрадь','карандаш','линейка'],
    ['ручка','ластик'],
    ['ручка','тетрадь','карандаш'],
]

class Node:
    _next_id = 0
    def __init__(self, item=None, parent=None):
        self.item, self.parent, self.count, self.children = item, parent, 0, {}
        self.id = Node._next_id; Node._next_id += 1

    def add(self, items, weight=1):
        current = self
        for item in items:
            if item not in current.children:
                current.children[item] = Node(item, current)
            current = current.children[item]
            current.count += weight

    def walk(self):
        yield self
        for ch in self.children.values():
            yield from ch.walk()

    def num_nodes(self):
        return sum(1 for _ in self.walk()) - 1

    def depth(self):
        if not self.children: return 0
        return 1 + max(ch.depth() for ch in self.children.values())


def read_bakery(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        if not {'Transaction', 'Item'}.issubset(r.fieldnames or []):
            raise ValueError('Expected CSV columns including Transaction and Item.')
        data = {}
        rows, removed = 0, 0
        for row in r:
            rows += 1
            item = row['Item'].strip()
            if not item or item.upper() == 'NONE':
                removed += 1
                continue
            tid = row['Transaction'].strip()
            if tid not in data: data[tid] = []
            data[tid].append(item)
    return [list(dict.fromkeys(items)) for items in data.values()], {'csv_rows':rows, 'removed':removed}


def prepare(transactions, min_support):
    trans = [list(dict.fromkeys(t)) for t in transactions]   # basket rather than quantities
    n = len(trans)
    threshold = math.ceil(n * min_support - 1e-10)
    counts = Counter(i for t in trans for i in t)
    order = sorted((i for i, c in counts.items() if c >= threshold), key=lambda i:(-counts[i],i.casefold()))
    rank = {it: j for j,it in enumerate(order)}
    sorted_t = [sorted((i for i in t if i in rank), key=rank.get) for t in trans]
    return counts, order, sorted_t, threshold


def build_tree(paths):
    root = Node()
    for path in paths:
        root.add(path)
    return root


def conditional_pattern_base(root, item):
    paths = []
    for node in root.walk():
        if node.item != item: continue
        prefix = []
        q = node.parent
        while q is not None and q.item is not None:
            prefix.append(q.item)
            q=q.parent
        if prefix:
            paths.append((list(reversed(prefix)), node.count))
    return paths


def conditional_fp_tree(base, threshold, global_order):
    counts = Counter()
    for prefix, weight in base:
        for item in prefix: counts[item] += weight
    kept = [i for i in global_order if counts[i] >= threshold]
    rank = {i: j for j,i in enumerate(kept)}
    tree = Node()
    for prefix, weight in base:
        path = sorted([i for i in prefix if i in rank], key=rank.get)
        if path: tree.add(path,weight)
    return tree, counts, kept


def itemset_summary(transactions, support_threshold):
    n=len(transactions)
    counter = Counter()
    for t in transactions:
        unique=sorted(set(t))
        for k in range(1, min(6,len(unique))+1):
            counter.update(combinations(unique,k))
    return [(list(items),freq,round(freq/n,6)) for items,freq in sorted(counter.items(),key=lambda z:(len(z[0]),-z[1],z[0])) if freq>=support_threshold]


def dot_for_tree(root, header_counts, active_path=None, max_depth=None, title='', parent_header=False):
    """Produce textbook-like graph: root above, item:count, dashed same-item links.
    When max_depth is set, expanded subtree counts are represented with a summary box.
    """
    active_path=active_path or []
    acc=[]
    acc.append('digraph fp {')
    acc.append('graph [rankdir=TB, bgcolor="white", splines=polyline, pad="0.42", nodesep="0.26", ranksep="0.63", outputorder="edgesfirst", fontname="DejaVu Sans", fontsize=16];')
    acc.append('node [shape=ellipse, style="filled", fillcolor="#d8eafd", color="#75a9d8", penwidth=1.5, fontname="DejaVu Sans", fontsize=11, fontcolor="#17365f", margin="0.12,0.09"];')
    acc.append('edge [color="#b4bfcc", arrowsize=0.56, penwidth=1.3];')
    if title: acc.append('labelloc="t"; label="'+title.replace('"','\\"')+'";')
    visible=[root]; links=[]; peritem=defaultdict(list)
    seen=set()
    def rec(node, depth=0, trace=None):
        trace=trace or []
        if node.item is None: label='ROOT'
        else: label=f'{node.item}: {node.count}'
        ident='n'+str(node.id)
        highlight = bool(active_path and trace and trace == active_path[:len(trace)])
        if node.item is None: style='fillcolor="#f2f4f8", color="#728096", fontcolor="#394150"'
        elif highlight: style='fillcolor="#ffe2af", color="#e39b21", penwidth=2.4'
        else: style=''
        acc.append(f'{ident} [label="{label}", {style}];')
        if node.item is not None: peritem[node.item].append(ident)
        if max_depth is not None and depth>=max_depth and node.children:
            desc=sum(1 for _ in node.walk())-1
            childid=f'z{node.id}'
            acc.append(f'{childid} [label="+{desc} additional nodes", shape=box, style="rounded,filled", fillcolor="#eef1f6", color="#d2d9e3", fontcolor="#596573", fontsize=9];')
            acc.append(f'{ident} -> {childid} [style=dotted];')
            return
        for child in node.children.values():
            acc.append(f'{ident} -> n{child.id};')
            rec(child,depth+1, trace+[child.item])
    rec(root)
    # Node-link chains (as dashed blue arrows). 'constraint=false' preserves the hierarchy.
    if max_depth is None:
        for it,nodes in peritem.items():
            for a,b in zip(nodes,nodes[1:]):
                acc.append(f'{a} -> {b} [style=dashed, constraint=false, color="#7182dc", penwidth=1.1, arrowsize=0.37];')
    acc.append('}')
    return '\n'.join(acc)


def dot_render(dot_code, destination, output_format='svg'):
    cmd = ['dot',f'-T{output_format}','-o',str(destination)]
    proc=subprocess.run(cmd,input=dot_code.encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode('utf-8','replace')[:3000])


def write_report_pdf(pdf_path, svg_files, captions, metadata):
    """PDF pages with a vector SVG diagram converted to PDF using CairoSVG.
    Each page has readable title, short evidence and the FP-tree graphic."""
    import fitz
    import cairosvg
    from io import BytesIO
    fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    doc=fitz.open()
    for j,(img_path, title, info) in enumerate(zip(svg_files,[x[0] for x in captions],[x[1] for x in captions]),1):
        # Set adaptive page width/height, maintain a reasonable on-screen diagram size.
        svgdata=Path(img_path).read_bytes()
        import re
        m=re.search(rb'<svg[^>]*\bwidth="([\d.]+)pt"[^>]*\bheight="([\d.]+)pt"',svgdata)
        if m: sw,sh=map(float,m.groups())
        else: sw,sh=960.,700.
        # Large trees use wider large-format pages so nodes are still legible when zoomed.
        pw=max(900,min(2400,sw+70)); ph=max(560,min(2300,sh+140))
        psvg=fitz.open(stream=cairosvg.svg2pdf(bytestring=svgdata),filetype='pdf')
        s=psvg[0].rect
        factor=min((pw-70)/s.width,(ph-150)/s.height)
        fitw,fith=s.width*factor,s.height*factor
        page=doc.new_page(width=pw,height=ph)
        tgt=fitz.Rect((pw-fitw)/2,110,(pw+fitw)/2,110+fith)
        page.show_pdf_page(tgt,psvg,0)
        # use PDF text font supporting Cyrillic via insertion from system (F0)
        page.insert_font(fontname='F0', fontfile=fontpath)
        page.insert_text((36,40),title,fontsize=17,fontname='F0',color=(.09,.20,.35))
        page.insert_text((36,67),info[:140],fontsize=10,fontname='F0',color=(.34,.39,.47))
        page.insert_text((pw-95,ph-23),f'{j} / {len(svg_files)}',fontsize=10,fontname='helv',color=(.45,.5,.56))
        psvg.close()
    doc.set_metadata({'title':metadata.get('name','FP-Growth diagrams')+' — step-by-step FP-tree diagrams', 'author':'FP-Growth diagram generator'})
    doc.save(pdf_path,garbage=4,deflate=True)
    doc.close()


def add_context_pages(pdf_path, metadata, paths):
    """Add explanatory frequency, sorted transactions, and summary pages to the tree book."""
    import fitz
    fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    pre=fitz.open()
    W,H=1190,842
    def start(title,subtitle):
        p=pre.new_page(width=W,height=H)
        p.insert_font(fontname='F0',fontfile=fontpath)
        p.draw_rect(fitz.Rect(0,0,W,95),color=None,fill=(.10,.16,.28))
        p.insert_text((42,45),title,fontname='F0',fontsize=22,color=(1,1,1))
        p.insert_text((42,74),subtitle,fontname='F0',fontsize=10.5,color=(.8,.87,.98))
        return p
    def line(p,x,y,s,size=11,col=(.12,.20,.35)):
        p.insert_text((x,y),str(s),fontname='F0',fontsize=size,color=col)
    def hr(p,y):
        p.draw_line((40,y),(W-40,y),color=(.84,.87,.91),width=.8)
    # Page 1: frequency header
    p=start('Этап 1 — подсчёт частот предметов',metadata['name'])
    line(p,45,134,f"Транзакций: {metadata['transactions']}  |  MinSupport: {metadata['min_support']*100:g}%  |  Минимальная частота: {metadata['threshold']}",13)
    line(p,45,162,'Все часто встречающиеся предметы остаются в FP-дереве.',11)
    hr(p,183)
    line(p,50,210,'Предмет',12)
    line(p,650,210,'Частота',12)
    line(p,800,210,'Поддержка',12)
    hr(p,219)
    for i,x in enumerate(metadata['frequency_order'][:32]):
        yy=250+i*17
        line(p,50,yy,x['item'],11)
        line(p,650,yy,x['support_count'],11)
        line(p,800,yy,f"{x['support']*100:.2f}%",11)
    pre_pages=len(pre)
    # Page 2: sorted transactions in two columns for first 30
    p=start('Этап 2 — сортировка транзакций','Предметы упорядочены по убыванию общей частоты, до построения дерева')
    m=min(30,len(paths))
    mid=(m+1)//2
    for idx, tx in enumerate(paths[:m]):
        x=45 if idx<mid else 613
        yy=132+(idx if idx<mid else idx-mid)*40
        text='  →  '.join(tx) if tx else '—'
        if len(text)>66:text=text[:65]+'…'
        line(p,x,yy,f'T{idx+1:02d}   {text}',10.7)
    line(p,47,795,'В следующих страницах показано FP-дерево после добавления каждой транзакции (или контрольных точек).',10)
    original=fitz.open(str(pdf_path))
    # append diagram pages
    pre.insert_pdf(original)
    original.close()
    # final information page
    p=pre.new_page(width=W,height=H)
    p.insert_font(fontname='F0',fontfile=fontpath)
    p.draw_rect(fitz.Rect(0,0,W,95),color=None,fill=(.10,.16,.28))
    line(p,45,43,'Итоги построения FP-дерева',20,(1,1,1))
    line(p,45,73,metadata['name'],11,(.8,.87,.98))
    line(p,45,130,f"Узлов без ROOT: {metadata['fp_tree_nodes_excluding_root']}  |  Глубина: {metadata['depth']}  |  Частота: {metadata['threshold']}",13)
    line(p,45,175,'Условные FP-деревья (для каждого суффикса)',12)
    hr(p,188)
    for j,cond in enumerate(metadata['conditional'][:20]):
        cy=217+j*22
        it=cond['item']; kept=', '.join(cond['frequent_prefix_items']) or 'нет частых предшественников'
        line(p,55,cy,f"{it}: {kept}",10.8)
    if metadata['frequent_itemsets']:
        line(p,45,405,'Частые предметные наборы (support ≥ minSup)',12)
        hr(p,416)
        for j,(items,freq,supp) in enumerate(metadata['frequent_itemsets'][:14]):
            line(p,50,446+j*23,(' + '.join(items))+f'   —   {freq}/30 ({supp*100:.2f}%)',10.7)
    else:
        line(p,45,704,'Для полного набора правил используйте программную реализацию FP-Growth.',11)
    pre.save(str(pdf_path)+'.new',garbage=4,deflate=True)
    pre.close()
    os.replace(str(pdf_path)+'.new',str(pdf_path))


def make_html(data, out_html, default_exercise):
    """Local, self-contained interactive explorer: transaction slider, full expandable tree.
    Bakery can be uploaded via CSV in the browser or loaded from the public canonical dataset.
    """
    template=Path(__file__).with_name('fpgrowth_explorer_template.html')
    if not template.exists():
        print('HTML template absent; skipped interactive explorer')
        return
    src=template.read_text(encoding='utf-8')
    src=src.replace('__STATIONERY_JSON__',json.dumps(STATIONERY,ensure_ascii=False))
    if data.get('exercise')=='bakery':
        src=src.replace('__BAKERY_JSON__',json.dumps(data['transactions'],ensure_ascii=False))
    else:
        src=src.replace('__BAKERY_JSON__','null')
    src=src.replace('__DEFAULT_EXERCISE__',default_exercise)
    out_html.write_text(src,encoding='utf-8')


def run(args):
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    if not shutil.which('dot'):
        raise EnvironmentError('Graphviz "dot" is required; install graphviz.')
    if args.exercise=='stationery':
        transactions=STATIONERY
        info={}
        min_support=.3
        label='STATIONERY — 30 transactions'
    else:
        if not args.csv:
            raise ValueError('Provide --csv BreadBasket_DMS.csv for the complete bakery tree.')
        transactions,info=read_bakery(args.csv)
        min_support=.005
        label='BREADBASKET — bakery transactions'
    counts, order, paths, threshold=prepare(transactions,min_support)
    root=Node()
    sizes=[]
    milestones=list(range(0,len(paths)+1)) if args.exercise=='stationery' else sorted(set([0,1,2,3,5,10,20,50,100,250,500,1000,2000,5000,len(paths)]))
    milestones=[m for m in milestones if m<=len(paths)]
    svgs=[]; captions=[]; snapshots=[]
    diagrams=out/'diagrams'; diagrams.mkdir(exist_ok=True)
    for idx, path in enumerate(paths,1):
        root.add(path)
        sizes.append(root.num_nodes())
        if idx not in milestones: continue
        headcounts=Counter(i for p in paths[:idx] for i in p)
        caption=f'Этап: после транзакции {idx} из {len(paths)}'
        safe_order=' → '.join(path) if path else '(no frequent items)'
        svg=diagrams/f'tree_{idx:05}.svg'
        maxdepth=None if args.exercise=='stationery' else 3
        dot=dot_for_tree(root,headcounts,active_path=path,max_depth=maxdepth, title='')
        dot_render(dot,svg,'svg')
        svgs.append(svg)
        captions.append((caption,'Added path: '+safe_order[:120]))
        snapshots.append({'stage':idx,'nodes':root.num_nodes(),'depth':root.depth(),'path':path})
    if 0 in milestones:
        svg=diagrams/'tree_00000.svg'
        initial=Node()
        dot_render(dot_for_tree(initial,Counter()),svg,'svg')
        svgs.insert(0,svg)
        captions.insert(0,('Этап: пустое дерево','Before inserting any transactions'))
    full_final=diagrams/'final_full_tree.svg'
    if args.exercise=='stationery':
        dot_render(dot_for_tree(root,counts),full_final,'svg')
        # ensure full final independently visible
        dot_render(dot_for_tree(root,counts),diagrams/'FINAL_FP_TREE.svg','svg')
    else:
        # full tree might have thousands of nodes and enormous page size; explorer renders all nodes interactively.
        dot_render(dot_for_tree(root,counts,max_depth=4),diagrams/'FINAL_FP_TREE_OVERVIEW.svg','svg')
    # Conditional pattern bases + conditional trees for EVERY frequent item, PDF a smaller selected subset for bakery.
    conditions=[]
    items_cond= list(reversed(order)) if args.exercise=='stationery' else list(reversed(order[:min(10,len(order))]))
    for item in items_cond:
        base=conditional_pattern_base(root,item)
        conditional, condcounts, kept=conditional_fp_tree(base,threshold,order)
        conditions.append({'item':item,'pattern_base':[{'prefix':p,'weight':w} for p,w in base],
                           'conditional_counts':dict(sorted(condcounts.items(),key=lambda kv:-kv[1])),
                           'frequent_prefix_items':kept,'conditional_nodes':conditional.num_nodes(),
                           'conditional_tree_exists':bool(conditional.children)})
        f=diagrams/(f'conditional_{order.index(item)+1:02}.svg')
        dot_render(dot_for_tree(conditional,condcounts,max_depth=3 if args.exercise=='bakery' else None),f,'svg')
        svgs.append(f)
        brief=', '.join(f'{i}={condcounts[i]}' for i in kept) if kept else 'No frequent prefix items'
        captions.append((f'Условное FP-дерево: {item}', 'Frequent prefix counts: '+brief[:130]))
    fp=itemset_summary(transactions,threshold) if args.exercise=='stationery' else []
    metadata={'exercise':args.exercise,'name':label,'transactions':len(paths),
              'min_support':min_support,'threshold':threshold,'min_confidence':.6,
              'frequency_order':[{'item':i,'support_count':counts[i],'support':round(counts[i]/len(paths),6)} for i in order],
              'fp_tree_nodes_excluding_root':root.num_nodes(),'depth':root.depth(),
              'milestone_snapshots':snapshots,'conditional':conditions,'frequent_itemsets':fp, 'csv_info':info,
              'tie_break_rule':'Descending basket frequency, then item name lexicographically; duplicates in each basket removed.'}
    (out/'FP_Growth_calculations.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    with open(out/'sorted_transactions.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['transaction_number','sorted_frequent_items'])
        for j,p in enumerate(paths,1): w.writerow([j,' → '.join(p)])
    pdf=out/('FP_Growth_'+args.exercise+'_stages.pdf')
    write_report_pdf(pdf,svgs,captions,metadata)
    add_context_pages(pdf,metadata,paths)
    make_html({'exercise':args.exercise,'transactions':transactions},out/'FP_Growth_interactive.html',args.exercise)
    print(json.dumps({'name':label,'transactions':len(paths),'threshold':threshold,'order':[(i,counts[i]) for i in order],
                    'node_count':root.num_nodes(),'depth':root.depth(), 'stages_in_pdf':len(svgs),
                    'pdf':str(pdf),'interactive':str(out/'FP_Growth_interactive.html')},ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--exercise',choices=['stationery','bakery'],required=True)
    parser.add_argument('--csv',default=None)
    parser.add_argument('--output',default='fp_output')
    run(parser.parse_args())