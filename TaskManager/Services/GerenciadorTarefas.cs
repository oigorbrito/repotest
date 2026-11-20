using TaskManager.Models;

namespace TaskManager.Services
{
    /// <summary>
    /// Gerencia as operações de negócio das tarefas.
    /// </summary>
    public class GerenciadorTarefas
    {
        private readonly TarefaRepositorio _repositorio;
        private List<Tarefa> _tarefas;
        private int _proximoId;

        public GerenciadorTarefas(TarefaRepositorio repositorio)
        {
            _repositorio = repositorio;
            _tarefas = _repositorio.Carregar();
            _proximoId = _tarefas.Any() ? _tarefas.Max(t => t.Id) + 1 : 1;
        }

        public void Adicionar(Tarefa tarefa)
        {
            if (string.IsNullOrWhiteSpace(tarefa.Titulo))
                throw new ArgumentException("O título da tarefa é obrigatório.");

            tarefa.Id = _proximoId++;
            tarefa.DataCriacao = DateTime.Now;
            _tarefas.Add(tarefa);
            _repositorio.Salvar(_tarefas);
        }

        public List<Tarefa> ListarTodas()
        {
            return _tarefas.OrderByDescending(t => t.DataCriacao).ToList();
        }

        public List<Tarefa> ListarPendentes()
        {
            return _tarefas.Where(t => !t.Concluida).OrderByDescending(t => t.DataCriacao).ToList();
        }

        public List<Tarefa> ListarConcluidas()
        {
            return _tarefas.Where(t => t.Concluida).OrderByDescending(t => t.DataConclusao).ToList();
        }

        public List<Tarefa> ListarVencidas()
        {
            return _tarefas
                .Where(t => !t.Concluida && t.DataPrazo.HasValue && t.DataPrazo.Value < DateTime.Now)
                .OrderBy(t => t.DataPrazo)
                .ToList();
        }

        public List<Tarefa> FiltrarPorPrioridade(PrioridadeTarefa prioridade)
        {
            return _tarefas.Where(t => t.Prioridade == prioridade).OrderByDescending(t => t.DataCriacao).ToList();
        }

        public Tarefa? BuscarPorId(int id)
        {
            return _tarefas.FirstOrDefault(t => t.Id == id);
        }

        public bool Concluir(int id)
        {
            var tarefa = BuscarPorId(id);
            if (tarefa == null)
                return false;

            if (tarefa.Concluida)
                return false;

            tarefa.Concluida = true;
            tarefa.DataConclusao = DateTime.Now;
            _repositorio.Salvar(_tarefas);
            return true;
        }

        public bool Reabrir(int id)
        {
            var tarefa = BuscarPorId(id);
            if (tarefa == null || !tarefa.Concluida)
                return false;

            tarefa.Concluida = false;
            tarefa.DataConclusao = null;
            _repositorio.Salvar(_tarefas);
            return true;
        }

        public bool Editar(int id, string novoTitulo, string novaDescricao, DateTime? novoPrazo, PrioridadeTarefa novaPrioridade)
        {
            var tarefa = BuscarPorId(id);
            if (tarefa == null)
                return false;

            if (string.IsNullOrWhiteSpace(novoTitulo))
                throw new ArgumentException("O título não pode ser vazio.");

            tarefa.Titulo = novoTitulo;
            tarefa.Descricao = novaDescricao;
            tarefa.DataPrazo = novoPrazo;
            tarefa.Prioridade = novaPrioridade;
            _repositorio.Salvar(_tarefas);
            return true;
        }

        public bool Excluir(int id)
        {
            var tarefa = BuscarPorId(id);
            if (tarefa == null)
                return false;

            _tarefas.Remove(tarefa);
            _repositorio.Salvar(_tarefas);
            return true;
        }

        public int TotalTarefas => _tarefas.Count;
        public int TotalPendentes => _tarefas.Count(t => !t.Concluida);
        public int TotalConcluidas => _tarefas.Count(t => t.Concluida);
    }
}
