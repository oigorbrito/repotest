using System.Text.Json;
using System.Text.Json.Serialization;
using TaskManager.Models;

namespace TaskManager.Services
{
    /// <summary>
    /// Responsável por salvar e carregar as tarefas em um arquivo JSON.
    /// </summary>
    public class TarefaRepositorio
    {
        private readonly string _caminhoArquivo;
        private readonly JsonSerializerOptions _opcoes;

        public TarefaRepositorio(string caminhoArquivo)
        {
            _caminhoArquivo = caminhoArquivo;
            _opcoes = new JsonSerializerOptions
            {
                WriteIndented = true,
                ReferenceHandler = ReferenceHandler.IgnoreCycles,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            };
        }

        public List<Tarefa> Carregar()
        {
            if (!File.Exists(_caminhoArquivo))
                return new List<Tarefa>();

            try
            {
                string json = File.ReadAllText(_caminhoArquivo);
                if (string.IsNullOrWhiteSpace(json))
                    return new List<Tarefa>();

                var tarefas = JsonSerializer.Deserialize<List<Tarefa>>(json, _opcoes);
                return tarefas ?? new List<Tarefa>();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Erro ao carregar tarefas: {ex.Message}");
                return new List<Tarefa>();
            }
        }

        public void Salvar(List<Tarefa> tarefas)
        {
            try
            {
                string pasta = Path.GetDirectoryName(_caminhoArquivo);
                if (!string.IsNullOrEmpty(pasta) && !Directory.Exists(pasta))
                    Directory.CreateDirectory(pasta);

                string json = JsonSerializer.Serialize(tarefas, _opcoes);
                File.WriteAllText(_caminhoArquivo, json);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Erro ao salvar tarefas: {ex.Message}");
                throw;
            }
        }
    }
}
