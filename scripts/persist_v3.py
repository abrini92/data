def p_haut(changes, K=12, lo=0.05, hi=0.95):
    c = changes[-K:]
    st = [1 if x > 0 else 0 for x in c]  # zero or down = non-hausse
    m = len(st); h = sum(st)
    if m < 3: return 0.5, "0,5 + justification"
    f = (h + 1) / (m + 2)
    n = m - 1
    if n < 6: return min(hi, max(lo, f)), "f"
    d = st[-1]
    nd = sum(1 for i in range(n) if st[i] == d)
    ud = sum(1 for i in range(n) if st[i] == d and st[i+1] == 1)
    p = (ud + 4*f) / (nd + 4)
    return min(hi, max(lo, p)), f"markov nd={nd} ud={ud} f={f:.4f} raw={p:.4f}"
T = {
 "tendance": [1,1,1,1,-1,1,1,1,1,1,1,-1],
 "12 hausses": [1]*12,
 "alternance 11": [1,-1]*5+[1],
 "4 var 3 hausses": [1,1,-1,1],
 "zeros": [1,0,1,0,1,0,1],
 "2 var": [1,1],
}
for k,v in T.items(): print(k, p_haut(v))
