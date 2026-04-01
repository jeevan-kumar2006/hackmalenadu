"""Concept extraction from source code and markdown files."""
import re
import ast
import math
from collections import Counter

STOP_WORDS = {
    'the','a','an','and','or','but','in','on','at','to','for','of','with',
    'by','from','is','are','was','were','be','been','being','have','has',
    'had','do','does','did','will','would','could','should','may','might',
    'can','shall','not','no','nor','this','that','these','those','it','its',
    'we','you','he','she','they','them','their','what','which','who','where',
    'when','how','why','if','then','else','so','as','up','out','about',
    'into','over','after','before','between','under','through','during',
    'also','just','very','often','however','too','only','than','such','both',
    'each','every','all','any','few','more','most','other','some','well',
    'back','even','still','way','take','come','make','like','long','get',
    'much','now','new','one','two','first','last','use','used','using',
    'need','example','based','note','notes','file','files','code','let',
    'var','const','func','return','true','false','none','null','self',
    'main','args','print','printf','cout','cin','std','endl','include',
    'define','ifdef','ifndef','endif','pragma','int','void','char',
    'float','double','bool','string','auto','register','extern','inline',
    'static','volatile','signed','unsigned','short','long','sizeof',
    'goto','switch','case','break','continue','default','try','catch',
    'finally','throw','class','struct','enum','union','typedef','template',
    'namespace','using','public','private','protected','virtual','override',
    'abstract','interface','extends','implements','import','export','package',
    'super','this','new','delete','async','await','yield','lambda','def',
    'pass','global','nonlocal','del','assert','raise','with','as','from',
}


def normalize(name):
    """Lowercase, strip non-alphanumeric, split camelCase/snake_case."""
    name = name.lower().strip()
    # Split on non-alphanumeric
    parts = re.split(r'[^a-z0-9]+', name)
    # Further split camelCase
    expanded = []
    for p in parts:
        # Split "helloworld" at digit-letter boundaries
        sub = re.findall(r'[a-z]+|\d+', p)
        expanded.extend(sub)
    return [w for w in expanded if len(w) > 1 and w not in STOP_WORDS]


def extract_markdown(content):
    """Extract concepts from markdown: headings, bold, inline code, code lang tags."""
    concepts = []
    # Headings (### and below are more specific)
    for m in re.finditer(r'^#{1,6}\s+(.+)$', content, re.MULTILINE):
        concepts.extend(normalize(m.group(1)))
    # Bold text
    for m in re.finditer(r'\*\*(.+?)\*\*', content):
        concepts.extend(normalize(m.group(1)))
    # Inline code
    for m in re.finditer(r'`([^`]+)`', content):
        token = m.group(1).strip()
        if len(token) < 60:
            concepts.extend(normalize(token))
    # Code block language tags
    for m in re.finditer(r'```(\w+)', content):
        concepts.append(m.group(1).lower())
    # Plain word frequency (excluding code blocks)
    text = re.sub(r'```[\s\S]*?```', '', content)
    text = re.sub(r'[#*`\[\]\(\)>|-]', ' ', text)
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    concepts.extend(w for w in words if w not in STOP_WORDS)
    return concepts


def extract_python(content):
    """Extract concepts from Python using AST + regex fallback."""
    concepts = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                concepts.extend(normalize(node.name))
                # Extract docstring keywords
                if ast.get_docstring(node):
                    concepts.extend(normalize(ast.get_docstring(node)))
            elif isinstance(node, ast.ClassDef):
                concepts.extend(normalize(node.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    concepts.extend(normalize(alias.name.split('.')[-1]))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    concepts.extend(normalize(node.module.split('.')[-1]))
                for alias in (node.names or []):
                    concepts.extend(normalize(alias.name))
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                concepts.extend(normalize(node.id))
    except SyntaxError:
        # Fallback to regex
        for m in re.finditer(r'def\s+(\w+)', content):
            concepts.extend(normalize(m.group(1)))
        for m in re.finditer(r'class\s+(\w+)', content):
            concepts.extend(normalize(m.group(1)))
        for m in re.finditer(r'import\s+[\w.]+', content):
            concepts.extend(normalize(m.group(0).replace('import ', '')))
    return concepts


def extract_c(content):
    """Extract concepts from C/C++ using regex."""
    concepts = []
    # Function definitions
    for m in re.finditer(r'(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{', content):
        concepts.extend(normalize(m.group(1)))
    # Structs
    for m in re.finditer(r'struct\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Typedefs
    for m in re.finditer(r'typedef\s+.*?(\w+)\s*;', content):
        concepts.extend(normalize(m.group(1)))
    # Macros
    for m in re.finditer(r'#define\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Includes (just module name)
    for m in re.finditer(r'#include\s*[<"](\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Enums
    for m in re.finditer(r'enum\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Identifiers (variable names that look meaningful)
    for m in re.finditer(r'\b([a-z][a-z0-9_]{4,})\b', content):
        concepts.extend(normalize(m.group(1)))
    return concepts


def extract_js(content):
    """Extract concepts from JavaScript/TypeScript."""
    concepts = []
    # Function declarations
    for m in re.finditer(r'function\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Arrow functions / const assignments
    for m in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^)]*\)|async|\w+)\s*=>', content):
        concepts.extend(normalize(m.group(1)))
    # Classes
    for m in re.finditer(r'class\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Imports
    for m in re.finditer(r'import\s+.*?from\s*[\'"]([^"\']+)[\'"]', content):
        mod = m.group(1).split('/')[-1].replace('.js', '').replace('.ts', '')
        concepts.extend(normalize(mod))
    for m in re.finditer(r'require\s*\(\s*[\'"]([^"\']+)[\'"]', content):
        mod = m.group(1).split('/')[-1]
        concepts.extend(normalize(mod))
    # Exports
    for m in re.finditer(r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Interface/type (TypeScript)
    for m in re.finditer(r'(?:interface|type)\s+(\w+)', content):
        concepts.extend(normalize(m.group(1)))
    # Meaningful identifiers
    for m in re.finditer(r'\b([a-z][a-zA-Z0-9_]{3,})\b', content):
        concepts.extend(normalize(m.group(1)))
    return concepts


def extract_generic(content):
    """Fallback extraction: word frequency with stop-word filtering."""
    # Remove common code punctuation
    text = re.sub(r'[{}()\[\];,.<>:?!@#$%^&*=+/\\|~`"\']', ' ', content)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]


def extract_concepts(filename, content):
    """Route to the appropriate extractor based on file extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.md', '.markdown', '.rst'):
        raw = extract_markdown(content)
    elif ext == '.py':
        raw = extract_python(content)
    elif ext in ('.c', '.h'):
        raw = extract_c(content)
    elif ext in ('.cpp', '.hpp', '.cc', '.cxx'):
        raw = extract_c(content)  # C++ extraction is similar
    elif ext in ('.js', '.jsx', '.mjs', '.ts', '.tsx'):
        raw = extract_js(content)
    elif ext in ('.java', '.kt', '.scala'):
        raw = extract_js(content)  # Similar patterns
    elif ext in ('.rs',):
        raw = extract_c(content)  # Similar to C
    elif ext in ('.go',):
        raw = extract_js(content)  # Similar to JS
    else:
        raw = extract_generic(content)

    # Count and return with weights
    counter = Counter(raw)
    # Return as list of (concept, weight) sorted by weight desc
    total = sum(counter.values()) or 1
    return [(name, count / total) for name, count in counter.most_common(50)]
# Need os import at top level
import os
