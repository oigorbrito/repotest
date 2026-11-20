namespace TaskManager.Models
{
    /// <summary>
    /// Representa uma tarefa do gerenciador.
    /// </summary>
    public class Tarefa
    {
        public int Id { get; set; }
        public string Titulo { get; set; } = string.Empty;
        public string Descricao { get; set; } = string.Empty;
        public DateTime DataCriacao { get; set; } = DateTime.Now;
        public DateTime? DataPrazo { get; set; }
        public DateTime? DataConclusao { get; set; }
        public bool Concluida { get; set; }
        public PrioridadeTarefa Prioridade { get; set; } = PrioridadeTarefa.Media;
    }

    public enum PrioridadeTarefa
    {
        Baixa = 1,
        Media = 2,
        Alta = 3
    }
}
