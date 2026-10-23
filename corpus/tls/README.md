# Intermédiaire TLS public de HAS

Le 21 octobre 2026, `www.has-sante.fr` envoyait son certificat serveur sans le
certificat intermédiaire « Sectigo Public Server Authentication CA OV R36 ».
Un navigateur peut retrouver cet intermédiaire ; Requests ne le fait pas seul.

`sectigo-ov-r36.pem` est un **certificat public d'autorité intermédiaire**, sans
clé privée, récupéré à l'adresse AIA officielle :
`http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt`.
Avant utilisation, sa signature a été validée avec `openssl verify -CAfile`
contre les racines existantes de certifi. Son empreinte SHA-256 DER est :

```text
6542d176bed50f193c0ce297ae44ecd8a0a86bec2ede682769344059b4e78530
```

Le téléchargement essaie d'abord le mécanisme HTTPS normal. Seulement en cas
d'erreur TLS sur le domaine HAS, il ajoute cet intermédiaire épinglé à une copie
temporaire du bundle certifi. La validation de la chaîne, du nom et des dates
reste active ; `verify=False` n'est jamais utilisé. Aucun certificat système
n'est modifié. Une nouvelle erreur TLS reste bloquante.
