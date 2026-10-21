"""Seletores e scripts de extração do Portal da Transparência.

Tudo que depende do HTML do portal fica AQUI. Se o layout mudar, este é o
único arquivo a ajustar. Os scripts JS são genéricos (pares rótulo/valor e
tabelas) justamente para tolerar pequenas mudanças de layout.
"""

# --- URLs ---------------------------------------------------------------
PATH_BUSCA_PF = "/pessoa-fisica/busca/lista"
FILTRO_BENEFICIARIO_PARAM = "beneficiarioProgramaSocial"

# --- Geral --------------------------------------------------------------
COOKIES_ACEITAR = "#accept-all-btn"
AREA_PRINCIPAL = "main, #main-content, .main-content, body"

# Página de verificação humana do AWS WAF exibida no lugar do conteúdo
JS_VERIFICACAO_HUMANA = """
() => /human verification/i.test(document.title || '')
   || Boolean(document.querySelector('script[src*="awswaf"], #captcha-container, awswaf-captcha'))
"""

# --- Busca --------------------------------------------------------------
BUSCA_CONTADOR = "#countResultados"
BUSCA_LINK_RESULTADO = "#resultados a.link-busca-nome"

JS_BUSCA_CONCLUIDA = """
() => {
  const c = document.querySelector('#countResultados');
  const temContador = c && /\\d/.test(c.innerText || '');
  const temLinks = document.querySelectorAll('#resultados a.link-busca-nome').length > 0;
  return Boolean(temContador || temLinks);
}
"""

# --- Panorama da pessoa física -----------------------------------------
PANORAMA_DADOS = "section.dados-tabelados"

# Expande acordeões (ex.: "Recebimentos de recursos") dentro da área principal
JS_EXPANDIR_SECOES = """
(root) => {
  const scope = document.querySelector(root) || document.body;
  let n = 0;
  scope.querySelectorAll('button[aria-expanded="false"], [data-toggle="collapse"][aria-expanded="false"]')
    .forEach(b => { try { b.click(); n++; } catch (e) {} });
  return n;
}
"""

# Pares <strong>Rótulo</strong><span>Valor</span>
JS_DADOS_ROTULADOS = """
(root) => {
  const out = {};
  document.querySelectorAll(root).forEach(scope => {
    scope.querySelectorAll('strong').forEach(s => {
      const rotulo = (s.innerText || '').trim();
      if (!rotulo) return;
      let valor = '';
      const irmao = s.nextElementSibling;
      if (irmao) valor = (irmao.innerText || '').trim();
      else valor = (s.parentElement.innerText || '').replace(s.innerText, '').trim();
      if (!(rotulo in out)) out[rotulo] = valor;
    });
  });
  return out;
}
"""

# Todas as tabelas visíveis como {titulo, headers, rows}
JS_TABELAS = """
(root) => {
  const scope = document.querySelector(root) || document;
  return Array.from(scope.querySelectorAll('table')).map(t => {
    const headers = Array.from(t.querySelectorAll('thead th')).map(th => (th.innerText || '').trim());
    const rows = Array.from(t.querySelectorAll('tbody tr'))
      .map(tr => Array.from(tr.cells).map(td => (td.innerText || '').trim()))
      .filter(r => r.some(c => c));
    let titulo = t.caption ? t.caption.innerText.trim() : '';
    if (!titulo) {
      const bloco = t.closest('[id], section');
      const h = bloco ? bloco.querySelector('strong, h3, h4') : null;
      titulo = h ? (h.innerText || '').trim() : '';
    }
    return { titulo, headers, rows };
  }).filter(t => t.rows.length);
}
"""

# Links "Detalhar" de cada benefício recebido
JS_LINKS_BENEFICIOS = """
(root) => {
  const scope = document.querySelector(root) || document.body;
  return Array.from(scope.querySelectorAll('a'))
    .filter(a => /detalhar/i.test(a.innerText || '') && a.href)
    .map(a => {
      const linha = a.closest('tr');
      const bloco = a.closest('table') ? a.closest('table').closest('[id], section') : null;
      const h = bloco ? bloco.querySelector('strong, h3, h4') : null;
      return {
        href: a.href,
        titulo: h ? (h.innerText || '').trim() : '',
        linha: linha ? Array.from(linha.cells).map(c => (c.innerText || '').trim()) : [],
      };
    });
}
"""

# --- Detalhe do benefício ----------------------------------------------
DETALHE_TAMANHO_PAGINA = "select[name$='_length']"

JS_DETALHE_CARREGADO = """
() => {
  const vazio = /nenhum registro|não há registros|sem registros/i.test(document.body.innerText || '');
  const linha = document.querySelector('table tbody tr');
  const carregando = linha && /carregando|processando/i.test(linha.innerText || '');
  return vazio || (Boolean(linha) && !carregando);
}
"""
