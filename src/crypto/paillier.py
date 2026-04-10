import random, hashlib, json
from math import gcd

def is_prime(n, k=20):
    if n < 2: return False
    if n in (2,3): return True
    if n%2==0: return False
    r,d=0,n-1
    while d%2==0: r+=1; d//=2
    for _ in range(k):
        a=random.randrange(2,n-1); x=pow(a,d,n)
        if x in (1,n-1): continue
        for _ in range(r-1):
            x=pow(x,2,n)
            if x==n-1: break
        else: return False
    return True

def gen_prime(bits):
    while True:
        n=random.getrandbits(bits)|(1<<(bits-1))|1
        if is_prime(n): return n

def ext_gcd(a,b):
    if a==0: return b,0,1
    g,x,y=ext_gcd(b%a,a); return g,y-(b//a)*x,x

def mod_inv(a,m):
    g,x,_=ext_gcd(a,m)
    if g!=1: raise ValueError(f"No inverse: gcd({a%m},{m})={g}")
    return x%m

def lcm(a,b): return a*b//gcd(a,b)

def generate_keypair(bits=256):
    """Generate Paillier keypair. Returns (public_key, private_key)."""
    while True:
        p=gen_prime(bits); q=gen_prime(bits)
        if p==q: continue
        n=p*q
        if gcd(p*q,(p-1)*(q-1))!=1: continue
        break
    n_sq=n*n; g=n+1
    lam=lcm(p-1,q-1)
    mu=mod_inv(lam,n)
    pub={"n":n,"g":g,"n_sq":n_sq,"bits":bits}
    priv={"lam":lam,"mu":mu,"p":p,"q":q}
    return pub, priv

def encrypt(pk,m):
    n,g,n_sq=pk["n"],pk["g"],pk["n_sq"]
    assert 0<=m<n, f"Message {m} out of range"
    while True:
        r=random.randrange(2,n)
        if gcd(r,n)==1: break
    return (pow(g,m,n_sq)*pow(r,n,n_sq))%n_sq

def decrypt(pk,sk,c):
    n,n_sq=pk["n"],pk["n_sq"]
    lam,mu=sk["lam"],sk["mu"]
    L=lambda x:(x-1)//n
    return (L(pow(c,lam,n_sq))*mu)%n

def add_enc(pk,c1,c2): return (c1*c2)%pk["n_sq"]

def add_enc_list(pk,cs):
    acc=encrypt(pk,0)
    for c in cs: acc=add_enc(pk,acc,c)
    return acc

def share_secret(secret, threshold, n_shares):
    """
    Shamir's Secret Sharing over a prime field.
    Prime is always generated larger than the secret so reconstruction is exact.
    Returns (shares, prime) where shares = list of (x, y) tuples.
    """
    # prime must be strictly > secret; add 128 bits of headroom
    prime_bits = secret.bit_length() + 128
    while True:
        prime = gen_prime(max(prime_bits, 512))
        if prime > secret:
            break
    coeffs = [secret] + [random.randrange(1, prime) for _ in range(threshold-1)]
    def poly(x):
        result=0
        for i,c in enumerate(coeffs):
            result=(result + c*pow(x,i,prime)) % prime
        return result
    shares = [(i, poly(i)) for i in range(1, n_shares+1)]
    return shares, prime

def reconstruct_secret(shares, prime):
    """
    Lagrange interpolation mod prime.
    shares = list of (x, y) tuples — any threshold of them suffices.
    """
    xs=[s[0] for s in shares]
    ys=[s[1] for s in shares]
    def lagrange_coeff(i):
        xi=xs[i]; num=den=1
        for j,xj in enumerate(xs):
            if i!=j:
                num=(num * ((-xj) % prime)) % prime
                den=(den * ((xi-xj) % prime)) % prime
        return (num * mod_inv(den,prime)) % prime
    secret=0
    for i in range(len(shares)):
        secret=(secret + ys[i]*lagrange_coeff(i)) % prime
    return secret

def receipt_hash(voter_id,eid,ct):
    return hashlib.sha256(f"{voter_id}:{eid}:{ct}".encode()).hexdigest()

def audit_hash(event,payload):
    return hashlib.sha256(f"{event}:{json.dumps(payload,sort_keys=True)}".encode()).hexdigest()

def pk_to_dict(pk):
    return {k: hex(v) if isinstance(v,int) else v for k,v in pk.items()}

def pk_from_dict(d):
    return {k: int(v,16) if isinstance(v,str) and v.startswith("0x") else v for k,v in d.items()}
