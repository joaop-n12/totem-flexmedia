// Scanner temporario de erros ortograficos PT-BR em templates.
// Deletar apos uso.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, 'templates');

const ERROS = [
  [/\bNao\b/g, 'Não'], [/\bnao\b/g, 'não'],
  [/\bacao\b/g, 'ação'], [/\bAcao\b/g, 'Ação'],
  [/\bacoes\b/g, 'ações'], [/\bAcoes\b/g, 'Ações'],
  [/\bprogramacao\b/g, 'programação'], [/\bProgramacao\b/g, 'Programação'],
  [/\bsessao\b/g, 'sessão'], [/\bSessao\b/g, 'Sessão'],
  [/\bconfiguracao\b/g, 'configuração'], [/\bConfiguracao\b/g, 'Configuração'],
  [/\bvoce\b/g, 'você'], [/\bVoce\b/g, 'Você'],
  [/\batencao\b/g, 'atenção'], [/\bAtencao\b/g, 'Atenção'],
  [/\btambem\b/g, 'também'], [/\bTambem\b/g, 'Também'],
  [/\batraves\b/g, 'através'], [/\bAtraves\b/g, 'Através'],
  [/\btres\b/g, 'três'], [/\bTres\b/g, 'Três'],
  [/\bnivel\b/g, 'nível'], [/\bNivel\b/g, 'Nível'],
  [/\bfacil\b/g, 'fácil'], [/\bFacil\b/g, 'Fácil'],
  [/\bdificil\b/g, 'difícil'], [/\bDificil\b/g, 'Difícil'],
  [/\bpublico\b/g, 'público'], [/\bPublico\b/g, 'Público'],
  [/\busuario\b/g, 'usuário'], [/\bUsuario\b/g, 'Usuário'],
  [/\busuarios\b/g, 'usuários'], [/\bUsuarios\b/g, 'Usuários'],
  [/\bconexao\b/g, 'conexão'], [/\bConexao\b/g, 'Conexão'],
  [/\bopcao\b/g, 'opção'], [/\bOpcao\b/g, 'Opção'],
  [/\bopcoes\b/g, 'opções'], [/\bOpcoes\b/g, 'Opções'],
  [/\binformacao\b/g, 'informação'], [/\bInformacao\b/g, 'Informação'],
  [/\binformacoes\b/g, 'informações'], [/\bInformacoes\b/g, 'Informações'],
  [/\binstituicao\b/g, 'instituição'], [/\bInstituicao\b/g, 'Instituição'],
  [/\binstituicoes\b/g, 'instituições'], [/\bInstituicoes\b/g, 'Instituições'],
  [/\bperiodo\b/g, 'período'], [/\bPeriodo\b/g, 'Período'],
  [/\bautomatico\b/g, 'automático'], [/\bAutomatico\b/g, 'Automático'],
  [/\bhorarios\b/g, 'horários'], [/\bHorarios\b/g, 'Horários'],
  [/\bhorario\b/g, 'horário'], [/\bHorario\b/g, 'Horário'],
  [/\bja\b/g, 'já'], [/\bate\b/g, 'até'],
  [/\bRelatorio\b/g, 'Relatório'], [/\brelatorio\b/g, 'relatório'],
  [/\bRelatorios\b/g, 'Relatórios'], [/\brelatorios\b/g, 'relatórios'],
  [/\bExperiencia\b/g, 'Experiência'], [/\bexperiencia\b/g, 'experiência'],
  [/\bCodigo\b/g, 'Código'], [/\bcodigo\b/g, 'código'],
  [/\bCodigos\b/g, 'Códigos'], [/\bcodigos\b/g, 'códigos'],
  [/\bMinimo\b/g, 'Mínimo'], [/\bminimo\b/g, 'mínimo'],
  [/\bMaximo\b/g, 'Máximo'], [/\bmaximo\b/g, 'máximo'],
  [/\bUltimo\b/g, 'Último'], [/\bultimo\b/g, 'último'],
  [/\bUltima\b/g, 'Última'], [/\bultima\b/g, 'última'],
  [/\bdescricao\b/g, 'descrição'], [/\bDescricao\b/g, 'Descrição'],
  [/\bestao\b/g, 'estão'], [/\bEstao\b/g, 'Estão'],
  [/\bsao\b/g, 'são'], [/\bSao\b/g, 'São'],
  [/\baudio\b/g, 'áudio'], [/\bAudio\b/g, 'Áudio'],
  [/\bvisao\b/g, 'visão'], [/\bVisao\b/g, 'Visão'],
  [/\bdecisao\b/g, 'decisão'], [/\bDecisao\b/g, 'Decisão'],
  [/\binicio\b/g, 'início'], [/\bInicio\b/g, 'Início'],
  [/\btermino\b/g, 'término'], [/\bTermino\b/g, 'Término'],
  [/\binclusao\b/g, 'inclusão'], [/\bInclusao\b/g, 'Inclusão'],
  [/\bedicao\b/g, 'edição'], [/\bEdicao\b/g, 'Edição'],
  [/\bexibicao\b/g, 'exibição'], [/\bExibicao\b/g, 'Exibição'],
  [/\bgravacao\b/g, 'gravação'], [/\bGravacao\b/g, 'Gravação'],
  [/\binstalacao\b/g, 'instalação'], [/\bInstalacao\b/g, 'Instalação'],
  [/\bvalidacao\b/g, 'validação'], [/\bValidacao\b/g, 'Validação'],
  [/\bavaliacao\b/g, 'avaliação'], [/\bAvaliacao\b/g, 'Avaliação'],
  [/\bautenticacao\b/g, 'autenticação'], [/\bAutenticacao\b/g, 'Autenticação'],
  [/\bautorizacao\b/g, 'autorização'], [/\bAutorizacao\b/g, 'Autorização'],
  [/\boperacao\b/g, 'operação'], [/\bOperacao\b/g, 'Operação'],
  [/\baceitacao\b/g, 'aceitação'], [/\bAceitacao\b/g, 'Aceitação'],
  [/\bproducao\b/g, 'produção'], [/\bProducao\b/g, 'Produção'],
  [/\bnumero\b/g, 'número'], [/\bNumero\b/g, 'Número'],
  [/\bnumeros\b/g, 'números'], [/\bNumeros\b/g, 'Números'],
  [/\bareas\b/g, 'áreas'], [/\bAreas\b/g, 'Áreas'],
  [/\barea\b/g, 'área'], [/\bArea\b/g, 'Área'],
  [/\bemail\b/g, 'e-mail'],  // ok pode ser opcional
  [/\bproximo\b/g, 'próximo'], [/\bProximo\b/g, 'Próximo'],
  [/\bproxima\b/g, 'próxima'], [/\bProxima\b/g, 'Próxima'],
  [/\bja\b/g, 'já'], [/\bJa\b/g, 'Já'],
  [/\bpais\b/g, 'país'], [/\bPais\b/g, 'País'],
  [/\bsobera\b/g, 'soberá'],  // dummy
  [/\bservico\b/g, 'serviço'], [/\bServico\b/g, 'Serviço'],
  [/\bservicos\b/g, 'serviços'], [/\bServicos\b/g, 'Serviços'],
  [/\bproprio\b/g, 'próprio'], [/\bProprio\b/g, 'Próprio'],
  [/\bpropria\b/g, 'própria'], [/\bPropria\b/g, 'Própria'],
];

function walk(dir, out) {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, f.name);
    if (f.isDirectory()) walk(p, out);
    else if (p.endsWith('.html')) out.push(p);
  }
}
const files = [];
walk(ROOT, files);

const findings = [];
for (const file of files) {
  const content = fs.readFileSync(file, 'utf8');
  const rel = path.relative(__dirname, file);
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const [re, certo] of ERROS) {
      let m;
      const localRe = new RegExp(re.source, 'g');
      while ((m = localRe.exec(line)) !== null) {
        const start = Math.max(0, m.index - 100);
        const ctx = line.slice(start, m.index);
        // Ignora se dentro de atributo tecnico
        const inAttr = /(?:\b(?:name|id|class|value|for|type|src|href|action|data-[a-z-]+|rel|method|enctype)\s*=\s*["'][^"'<>]*$)/i.test(ctx);
        if (inAttr) continue;
        // Ignora dentro de {% %} ou {{ }}
        const bef = line.slice(0, m.index);
        const oJ = bef.lastIndexOf('{%'), cJ = bef.lastIndexOf('%}');
        if (oJ > cJ) continue;
        const oV = bef.lastIndexOf('{{'), cV = bef.lastIndexOf('}}');
        if (oV > cV) continue;
        // Ignora dentro de url_for(...) or quoted slug
        // ja coberto acima pelo {{ }} check
        findings.push({ file: rel, ln: i+1, word: m[0], certo, line: line.trim().slice(0, 220) });
      }
    }
  }
}

const byFile = {};
for (const f of findings) (byFile[f.file] ||= []).push(f);

const keys = Object.keys(byFile).sort();
console.log(`TOTAL: ${findings.length} ocorrencias em ${keys.length} arquivos\n`);
for (const k of keys) {
  console.log(`\n=== ${k} (${byFile[k].length}) ===`);
  for (const f of byFile[k]) {
    console.log(`L${f.ln} "${f.word}" -> "${f.certo}"`);
    console.log(`   ${f.line}`);
  }
}
