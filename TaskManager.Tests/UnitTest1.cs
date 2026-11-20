using System.Text.Json;
using TaskManager.Models;
using TaskManager.Services;

namespace TaskManager.Tests;

public class TarefaTests
{
    [Fact]
    public void Tarefa_PrioridadeAlta_EnumValido()
    {
        var tarefa = new Tarefa { Prioridade = PrioridadeTarefa.Alta };
        Assert.Equal(PrioridadeTarefa.Alta, tarefa.Prioridade);
    }
}

public class TarefaRepositorioTests
{
    private readonly string _caminhoArquivo;

    public TarefaRepositorioTests()
    {
        _caminhoArquivo = Path.Combine(Path.GetTempPath(), $"test_{Guid.NewGuid():N}.json");
    }

    [Fact]
    public void Repositorio_Carregar_QuandoNaoExiste_RetornaListaVazia()
    {
        var repositorio = new TarefaRepositorio(_caminhoArquivo);
        var tarefas = repositorio.Carregar();
        Assert.Empty(tarefas);
    }

    [Fact]
    public void Repositorio_Salvar_E_Carregar_DeveManterDados()
    {
        var repositorio = new TarefaRepositorio(_caminhoArquivo);
        var tarefa = new Tarefa { Titulo = "Teste Persistência", Prioridade = PrioridadeTarefa.Alta };
        repositorio.Salvar(new List<Tarefa> { tarefa });
        var tarefasCarregadas = repositorio.Carregar();
        Assert.Single(tarefasCarregadas);
        Assert.Equal("Teste Persistência", tarefasCarregadas[0].Titulo);
        Assert.Equal(PrioridadeTarefa.Alta, tarefasCarregadas[0].Prioridade);
    }

    [Fact]
    public void Repositorio_Salvar_ListaVazia_CriaArquutoVazio()
    {
        var repositorio = new TarefaRepositorio(_caminhoArquivo);
        repositorio.Salvar(new List<Tarefa>());
        var exists = File.Exists(_caminhoArquivo);
        Assert.True(exists);
    }

    [Fact]
    public void Repositorio_Salvar_E_Carregar_MultipleTarefas()
    {
        var repositorio = new TarefaRepositorio(_caminhoArquivo);
        var tarefas = new List<Tarefa>
        {
            new() { Titulo = "Tarefa 1", Prioridade = PrioridadeTarefa.Baixa },
            new() { Titulo = "Tarefa 2", Prioridade = PrioridadeTarefa.Alta },
            new() { Titulo = "Tarefa 3", Prioridade = PrioridadeTarefa.Media }
        };
        repositorio.Salvar(tarefas);
        var carregadas = repositorio.Carregar();
        Assert.Equal(3, carregadas.Count);
        Assert.Equal("Tarefa 1", carregadas[0].Titulo);
        Assert.Equal("Tarefa 2", carregadas[1].Titulo);
        Assert.Equal("Tarefa 3", carregadas[2].Titulo);
    }
}

public class GerenciadorTarefasTests : IDisposable
{
    private readonly string _caminhoArquivo;
    private readonly GerenciadorTarefas _gerenciador;

    public GerenciadorTarefasTests()
    {
        _caminhoArquivo = Path.Combine(Path.GetTempPath(), $"test_ger_{Guid.NewGuid():N}.json");
        var repositorio = new TarefaRepositorio(_caminhoArquivo);
        _gerenciador = new GerenciadorTarefas(repositorio);
    }

    [Fact]
    public void Gerenciador_Adicionar_Tarefa_IncrementaId()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Tarefa 1" });
        _gerenciador.Adicionar(new Tarefa { Titulo = "Tarefa 2" });
        var todas = _gerenciador.ListarTodas();
        Assert.Equal(2, todas.Count);
        Assert.Equal(1, todas[0].Id);
        Assert.Equal(2, todas[1].Id);
    }

    [Fact]
    public void Gerenciador_Adicionar_ListaVazia_PrimeiroIdEh1()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Primeira" });
        var todas = _gerenciador.ListarTodas();
        Assert.Single(todas);
        Assert.Equal(1, todas[0].Id);
    }

    [Fact]
    public void Gerenciador_Concluir_Tarefa_ValidaId()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Teste Concluir" });
        var resultado = _gerenciador.Concluir(1);
        Assert.True(resultado);
        var tarefa = _gerenciador.BuscarPorId(1);
        Assert.True(tarefa!.Concluida);
        Assert.NotNull(tarefa.DataConclusao);
    }

    [Fact]
    public void Gerenciador_Concluir_TarefaInexistente_RetornaFalse()
    {
        var resultado = _gerenciador.Concluir(999);
        Assert.False(resultado);
    }

    [Fact]
    public void Gerenciador_Excluir_Tarefa_RemoveDaLista()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Para Excluir" });
        _gerenciador.Adicionar(new Tarefa { Titulo = "Manter" });
        _gerenciador.Excluir(1);
        var todas = _gerenciador.ListarTodas();
        Assert.Single(todas);
        Assert.Equal("Manter", todas[0].Titulo);
    }

    [Fact]
    public void Gerenciador_ListarPendentes_ApenasNaoConcluidas()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Pendente" });
        _gerenciador.Adicionar(new Tarefa { Titulo = "Concluida", Concluida = true });
        var pendentes = _gerenciador.ListarPendentes();
        Assert.Single(pendentes);
        Assert.Equal("Pendente", pendentes[0].Titulo);
    }

    [Fact]
    public void Gerenciador_FiltrarPorPrioridade_Media_ApenasTarefasMedia()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Baixa", Prioridade = PrioridadeTarefa.Baixa });
        _gerenciador.Adicionar(new Tarefa { Titulo = "Media", Prioridade = PrioridadeTarefa.Media });
        _gerenciador.Adicionar(new Tarefa { Titulo = "Alta", Prioridade = PrioridadeTarefa.Alta });
        var media = _gerenciador.FiltrarPorPrioridade(PrioridadeTarefa.Media);
        Assert.Single(media);
        Assert.Equal("Media", media[0].Titulo);
    }

    [Fact]
    public void Gerenciador_ListarVencidas_SemPrazo_NaoInclui()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Sem Prazo" });
        _gerenciador.Adicionar(new Tarefa
        {
            Titulo = "Vencida",
            DataPrazo = DateTime.Now.AddDays(-5),
            Prioridade = PrioridadeTarefa.Alta
        });
        var vencidas = _gerenciador.ListarVencidas();
        Assert.Single(vencidas);
        Assert.Equal("Vencida", vencidas[0].Titulo);
    }

    [Fact]
    public void Gerenciador_Estatisticas_ContaCorretamente()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "1" });
        _gerenciador.Adicionar(new Tarefa { Titulo = "2", Concluida = true });
        _gerenciador.Adicionar(new Tarefa { Titulo = "3", Concluida = true });
        var total = _gerenciador.TotalTarefas;
        var pendentes = _gerenciador.TotalPendentes;
        var concluidas = _gerenciador.TotalConcluidas;
        Assert.Equal(3, total);
        Assert.Equal(2, concluidas);
        Assert.Equal(1, pendentes);
    }

    [Fact]
    public void Gerenciador_Reabrir_TarefaConcluida()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Teste Reabrir" });
        _gerenciador.Concluir(1);
        var resultado = _gerenciador.Reabrir(1);
        Assert.True(resultado);
        var tarefa = _gerenciador.BuscarPorId(1);
        Assert.False(tarefa!.Concluida);
        Assert.Null(tarefa.DataConclusao);
    }

    [Fact]
    public void Gerenciador_Editar_AtualizaDados()
    {
        _gerenciador.Adicionar(new Tarefa { Titulo = "Antiga", Descricao = "Descrição antiga", Prioridade = PrioridadeTarefa.Baixa });
        var atualizado = _gerenciador.Editar(1, "Nova", "Nova descrição", null, PrioridadeTarefa.Alta);
        Assert.True(atualizado);
        var tarefa = _gerenciador.BuscarPorId(1);
        Assert.Equal("Nova", tarefa!.Titulo);
        Assert.Equal("Nova descrição", tarefa.Descricao);
        Assert.Equal(PrioridadeTarefa.Alta, tarefa.Prioridade);
    }

    [Fact]
    public void Gerenciador_BuscarPorId_TarefaInexistente_ReturnsNull()
    {
        var tarefa = _gerenciador.BuscarPorId(999);
        Assert.Null(tarefa);
    }

    [Fact]
    public void Gerenciador_TotalDeTarefas_Zero_QuandoVazio()
    {
        Assert.Equal(0, _gerenciador.TotalTarefas);
        Assert.Equal(0, _gerenciador.TotalPendentes);
        Assert.Equal(0, _gerenciador.TotalConcluidas);
    }

    public void Dispose()
    {
        if (File.Exists(_caminhoArquivo))
            File.Delete(_caminhoArquivo);
    }
}