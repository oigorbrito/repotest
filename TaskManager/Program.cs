using TaskManager.Models;
using TaskManager.Services;

namespace TaskManager
{
    /// <summary>
    /// Interface de console do gerenciador de tarefas.
    /// </summary>
    public class Program
    {
        private static GerenciadorTarefas _gerenciador = null!;

        public static void Main(string[] args)
        {
            string caminhoArquivo = Path.Combine(AppContext.BaseDirectory, "tarefas.json");
            var repositorio = new TarefaRepositorio(caminhoArquivo);
            _gerenciador = new GerenciadorTarefas(repositorio);

            bool executando = true;

            Console.WriteLine("========================================");
            Console.WriteLine("   GERENCIADOR DE TAREFAS EM C#");
            Console.WriteLine("========================================");

            while (executando)
            {
                try
                {
                    ExibirMenu();
                    Console.Write("Escolha uma opção: ");
                    string opcao = Console.ReadLine()?.Trim() ?? string.Empty;

                    switch (opcao)
                    {
                        case "1":
                            AdicionarTarefa();
                            break;
                        case "2":
                            ListarTodasTarefas();
                            break;
                        case "3":
                            ListarTarefasPendentes();
                            break;
                        case "4":
                            ListarTarefasConcluidas();
                            break;
                        case "5":
                            ListarTarefasVencidas();
                            break;
                        case "6":
                            ConcluirTarefa();
                            break;
                        case "7":
                            EditarTarefa();
                            break;
                        case "8":
                            ExcluirTarefa();
                            break;
                        case "9":
                            FiltrarPorPrioridade();
                            break;
                        case "10":
                            ExibirEstatisticas();
                            break;
                        case "0":
                            executando = false;
                            Console.WriteLine("Encerrando o gerenciador de tarefas. Até mais!");
                            break;
                        default:
                            Console.WriteLine("Opção inválida. Tente novamente.");
                            break;
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Erro inesperado: {ex.Message}");
                }

                if (executando)
                {
                    Console.WriteLine();
                    Console.WriteLine("Pressione qualquer tecla para voltar ao menu...");
                    Console.ReadKey();
                    Console.Clear();
                }
            }
        }

        static void ExibirMenu()
        {
            Console.WriteLine("\n--- MENU ---");
            Console.WriteLine("1 - Adicionar tarefa");
            Console.WriteLine("2 - Listar todas as tarefas");
            Console.WriteLine("3 - Listar tarefas pendentes");
            Console.WriteLine("4 - Listar tarefas concluídas");
            Console.WriteLine("5 - Listar tarefas vencidas");
            Console.WriteLine("6 - Marcar tarefa como concluída");
            Console.WriteLine("7 - Editar tarefa");
            Console.WriteLine("8 - Excluir tarefa");
            Console.WriteLine("9 - Filtrar por prioridade");
            Console.WriteLine("10 - Estatísticas");
            Console.WriteLine("0 - Sair");
        }

        static void AdicionarTarefa()
        {
            Console.WriteLine("\n--- NOVA TAREFA ---");

            Console.Write("Título: ");
            string? titulo = Console.ReadLine();
            if (string.IsNullOrWhiteSpace(titulo))
            {
                Console.WriteLine("Erro: o título é obrigatório.");
                return;
            }

            Console.Write("Descrição: ");
            string? descricao = Console.ReadLine();

            Console.Write("Prazo (dd/MM/yyyy, deixe vazio para nenhum): ");
            string? prazoStr = Console.ReadLine();
            DateTime? prazo = null;
            if (!string.IsNullOrWhiteSpace(prazoStr))
            {
                if (!DateTime.TryParse(prazoStr, out DateTime dtPrazo))
                {
                    Console.WriteLine("Erro: data de prazo inválida.");
                    return;
                }
                if (dtPrazo.Date < DateTime.Today)
                {
                    Console.WriteLine("Erro: o prazo não pode ser uma data passada.");
                    return;
                }
                prazo = dtPrazo;
            }

            Console.Write("Prioridade (1-Baixa, 2-Média, 3-Alta): ");
            string? prioridadeStr = Console.ReadLine();
            PrioridadeTarefa prioridade = PrioridadeTarefa.Media;

            if (!string.IsNullOrWhiteSpace(prioridadeStr) && int.TryParse(prioridadeStr, out int p))
            {
                if (p < 1 || p > 3)
                {
                    Console.WriteLine("Erro: prioridade deve ser 1, 2 ou 3.");
                    return;
                }
                prioridade = (PrioridadeTarefa)p;
            }
            else if (!string.IsNullOrWhiteSpace(prioridadeStr))
            {
                Console.WriteLine("Erro: prioridade inválida.");
                return;
            }

            try
            {
                var tarefa = new Tarefa
                {
                    Titulo = titulo,
                    Descricao = descricao ?? string.Empty,
                    DataPrazo = prazo,
                    Prioridade = prioridade
                };
                _gerenciador.Adicionar(tarefa);
                Console.WriteLine($"Tarefa #{tarefa.Id} adicionada com sucesso!");
            }
            catch (ArgumentException ex)
            {
                Console.WriteLine($"Erro: {ex.Message}");
            }
        }

        static void ListarTodasTarefas()
        {
            ExibirLista(_gerenciador.ListarTodas(), "TODAS AS TAREFAS");
        }

        static void ListarTarefasPendentes()
        {
            ExibirLista(_gerenciador.ListarPendentes(), "TAREFAS PENDENTES");
        }

        static void ListarTarefasConcluidas()
        {
            ExibirLista(_gerenciador.ListarConcluidas(), "TAREFAS CONCLUÍDAS");
        }

        static void ListarTarefasVencidas()
        {
            ExibirLista(_gerenciador.ListarVencidas(), "TAREFAS VENCIDAS (PENDENTES COM PRAZO EXPIRADO)");
        }

        static void ExibirLista(List<Tarefa> tarefas, string titulo)
        {
            Console.WriteLine($"\n--- {titulo} ---");
            if (!tarefas.Any())
            {
                Console.WriteLine("Nenhuma tarefa encontrada.");
                return;
            }

            foreach (var t in tarefas)
            {
                string status = t.Concluida ? "[CONCLUÍDA]" : "[PENDENTE]";
                string prioridadeTexto = t.Prioridade switch
                {
                    PrioridadeTarefa.Baixa => "Baixa",
                    PrioridadeTarefa.Media => "Média",
                    PrioridadeTarefa.Alta => "Alta",
                    _ => "Média"
                };
                Console.WriteLine($"#{t.Id} {status} | Prioridade: {prioridadeTexto} | {t.Titulo}");
                Console.WriteLine($"      Criada em: {t.DataCriacao:dd/MM/yyyy HH:mm}");
                if (t.DataPrazo.HasValue)
                    Console.WriteLine($"      Prazo: {t.DataPrazo.Value:dd/MM/yyyy}");
                if (!string.IsNullOrWhiteSpace(t.Descricao))
                    Console.WriteLine($"      Descrição: {t.Descricao}");
                if (t.Concluida && t.DataConclusao.HasValue)
                    Console.WriteLine($"      Concluída em: {t.DataConclusao.Value:dd/MM/yyyy HH:mm}");
                Console.WriteLine();
            }
        }

        static void ConcluirTarefa()
        {
            Console.WriteLine("\n--- CONCLUIR TAREFA ---");
            Console.Write("ID da tarefa: ");
            if (int.TryParse(Console.ReadLine(), out int id))
            {
                if (_gerenciador.Concluir(id))
                    Console.WriteLine($"Tarefa #{id} marcada como concluída!");
                else
                    Console.WriteLine("Tarefa não encontrada ou já concluída.");
            }
            else
            {
                Console.WriteLine("ID inválido.");
            }
        }

        static void EditarTarefa()
        {
            Console.WriteLine("\n--- EDITAR TAREFA ---");
            Console.Write("ID da tarefa: ");
            if (!int.TryParse(Console.ReadLine(), out int id))
            {
                Console.WriteLine("ID inválido.");
                return;
            }

            var tarefa = _gerenciador.BuscarPorId(id);
            if (tarefa == null)
            {
                Console.WriteLine("Tarefa não encontrada.");
                return;
            }

            Console.Write($"Novo título ({tarefa.Titulo}): ");
            string? novoTitulo = Console.ReadLine();

            Console.Write($"Nova descrição ({tarefa.Descricao}): ");
            string? novaDescricao = Console.ReadLine();

            Console.Write($"Novo prazo (dd/MM/yyyy) [atual: {(tarefa.DataPrazo?.ToString("dd/MM/yyyy") ?? "nenhum")}]: ");
            string? novoPrazoStr = Console.ReadLine();
            DateTime? novoPrazo = tarefa.DataPrazo;
            if (!string.IsNullOrWhiteSpace(novoPrazoStr))
            {
                if (!DateTime.TryParse(novoPrazoStr, out DateTime dtNovoPrazo))
                {
                    Console.WriteLine("Erro: data de prazo inválida.");
                    return;
                }
                if (dtNovoPrazo.Date < DateTime.Today)
                {
                    Console.WriteLine("Erro: o prazo não pode ser uma data passada.");
                    return;
                }
                novoPrazo = dtNovoPrazo;
            }
            else if (string.IsNullOrWhiteSpace(novoPrazoStr))
            {
                novoPrazo = null;
            }

            Console.Write($"Nova prioridade (1-Baixa, 2-Média, 3-Alta) [atual: {(int)tarefa.Prioridade}]: ");
            string? prioridadeStr = Console.ReadLine();
            PrioridadeTarefa novaPrioridade = tarefa.Prioridade;
            if (!string.IsNullOrWhiteSpace(prioridadeStr) && int.TryParse(prioridadeStr, out int p))
            {
                if (p < 1 || p > 3)
                {
                    Console.WriteLine("Erro: prioridade deve ser 1, 2 ou 3.");
                    return;
                }
                novaPrioridade = (PrioridadeTarefa)p;
            }
            else if (!string.IsNullOrWhiteSpace(prioridadeStr))
            {
                Console.WriteLine("Erro: prioridade inválida.");
                return;
            }

            try
            {
                if (_gerenciador.Editar(id, string.IsNullOrWhiteSpace(novoTitulo) ? tarefa.Titulo : novoTitulo!,
                                       novaDescricao ?? tarefa.Descricao, novoPrazo, novaPrioridade))
                    Console.WriteLine($"Tarefa #{id} atualizada com sucesso!");
                else
                    Console.WriteLine("Tarefa não encontrada.");
            }
            catch (ArgumentException ex)
            {
                Console.WriteLine($"Erro: {ex.Message}");
            }
        }

        static void ExcluirTarefa()
        {
            Console.WriteLine("\n--- EXCLUIR TAREFA ---");
            Console.Write("ID da tarefa: ");
            if (int.TryParse(Console.ReadLine(), out int id))
            {
                if (_gerenciador.Excluir(id))
                    Console.WriteLine($"Tarefa #{id} excluída com sucesso!");
                else
                    Console.WriteLine("Tarefa não encontrada.");
            }
            else
            {
                Console.WriteLine("ID inválido.");
            }
        }

        static void FiltrarPorPrioridade()
        {
            Console.WriteLine("\n--- FILTRAR POR PRIORIDADE ---");
            Console.WriteLine("1 - Baixa");
            Console.WriteLine("2 - Média");
            Console.WriteLine("3 - Alta");
            Console.Write("Escolha: ");
            if (int.TryParse(Console.ReadLine(), out int p))
            {
                var prioridade = (PrioridadeTarefa)p;
                var tarefas = _gerenciador.FiltrarPorPrioridade(prioridade);
                ExibirLista(tarefas, $"TAREFAS - PRIORIDADE {prioridade}");
            }
            else
            {
                Console.WriteLine("Opção inválida.");
            }
        }

        static void ExibirEstatisticas()
        {
            Console.WriteLine("\n--- ESTATÍSTICAS ---");
            Console.WriteLine($"Total de tarefas: {_gerenciador.TotalTarefas}");
            Console.WriteLine($"Pendentes: {_gerenciador.TotalPendentes}");
            Console.WriteLine($"Concluídas: {_gerenciador.TotalConcluidas}");
            if (_gerenciador.TotalTarefas > 0)
            {
                double percentual = (double)_gerenciador.TotalConcluidas / _gerenciador.TotalTarefas * 100;
                Console.WriteLine($"Taxa de conclusão: {percentual:F1}%");
            }
        }
    }
}
